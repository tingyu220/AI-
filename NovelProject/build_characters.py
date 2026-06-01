#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_characters.py — 从章节 frontmatter 提取人物/实体信息，构建双向链接笔记。

功能：
  1. 人物笔记：创建/更新，含出现章节列表 + 共现关系 + wikilink 已有"人际关系"段落
  2. 地点笔记（可选）：同逻辑，从 frontmatter.locations_involved 提取
  3. 未来扩展：势力/物品等实体，只需在 ENTITY_CONFIG 中添加一行即可

用法:
    python build_characters.py --novel "文明升阶"
    python build_characters.py                            # 处理所有小说
    python build_characters.py --novel "文明升阶" --types character,location

依赖: PyYAML (pip install pyyaml)
"""

import argparse
import io
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# YAML 加载
# ---------------------------------------------------------------------------
try:
    import yaml
except ImportError:
    try:
        from ruamel import yaml
    except ImportError:
        print("错误: 缺少 YAML 解析库。请安装 PyYAML 或 ruamel.yaml：", file=sys.stderr)
        print("  pip install pyyaml", file=sys.stderr)
        print("  pip install ruamel.yaml", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# 实体类型配置 —— 添加新类型只需在这里加一行
#   每个条目: (类型标识, 目录名, section标题, fm字段)
#   - 类型标识: 用于 --types 筛选和日志
#   - 目录名: 在 Novels/{小说}/ 下的子目录
#   - section标题: 在笔记中显示为 ## 出现章节 或 ## 出现位置 等
#   - fm字段: 章节 frontmatter 中对应的列表字段（如 characters_involved）
# ---------------------------------------------------------------------------
ENTITY_CONFIG = {
    "character": {
        "dir": "01_Characters",
        "section": "出现章节",
        "fm_field": "characters_involved",
        "new_fm_field": "new_characters",       # 首次出现的人物
        "rel_section": "共现人物",               # 自动生成的关系段落标题
        "note_prefix": "",
    },
    "location": {
        "dir": "06_Locations",
        "section": "出现章节",
        "fm_field": "locations_involved",
        "new_fm_field": "new_locations",
        "rel_section": "共现地点",
        "note_prefix": "#地点 ",
    },
    # 未来扩展示例：
    # "faction": {
    #     "dir": "07_Factions",
    #     "section": "出现章节",
    #     "fm_field": "factions_involved",
    #     "new_fm_field": "new_factions",
    #     "rel_section": "关联势力",
    #     "note_prefix": "#势力 ",
    # },
}


# ---------------------------------------------------------------------------
# 日志配置（Windows 下 GBK 终端使用 UTF-8 包装）
# ---------------------------------------------------------------------------
class _UTF8StreamHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__(stream=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                                  errors="replace"))


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s %(message)s",
    handlers=[_UTF8StreamHandler()],
)
log = logging.getLogger("build_chars")


# ===================================================================
#  工具函数
# ===================================================================

def parse_frontmatter(text: str):
    """解析 Markdown 的 YAML frontmatter，返回 (dict, body) 或 (None, text)。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, text
    return (data if isinstance(data, dict) else None, text[match.end():])


def extract_chapter_number(label: str) -> int | None:
    """从 '第N章' / '第N章 标题' 中提取数字。"""
    m = re.match(r"第(\d+)章", label)
    return int(m.group(1)) if m else None


def parse_list_section(body_text: str, heading_pattern: str) -> set[str]:
    """在 body 中找到匹配 heading_pattern 的 ## section，提取其下列表项文字。"""
    found: set[str] = set()
    in_section = False
    for line in body_text.splitlines():
        stripped = line.strip()
        if re.match(rf"^##\s+{re.escape(heading_pattern)}", stripped):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## "):
                break
            # 提取 [[xxx]] 或 裸文本
            for m in re.finditer(r"\[\[(.+?)\]\]", stripped):
                found.add(m.group(1))
            # 也尝试提取 **xxx** 格式的名字
            for m in re.finditer(r"\*\*(.+?)\*\*", stripped):
                found.add(m.group(1))
    return found


def replace_or_append_section(body_text: str, section_heading: str, links: list[str]) -> str:
    """替换或追加 body 中的一个 ## section，内容为 - [[link]] 列表。"""
    lines = body_text.splitlines()
    heading = f"## {section_heading}"
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start_idx = i
            break

    if start_idx is not None:
        end_idx = len(lines)
        for j in range(start_idx + 1, len(lines)):
            if re.match(r"^##\s", lines[j]):
                end_idx = j
                break
        new_lines = lines[: start_idx + 1]
        new_lines.extend(f"- [[{l}]]" for l in links)
        if end_idx < len(lines):
            new_lines.extend(lines[end_idx:])
        return "\n".join(new_lines)
    else:
        new_body = body_text.rstrip("\n") + "\n\n"
        new_body += f"{heading}\n"
        new_body += "\n".join(f"- [[{l}]]" for l in links) + "\n"
        return new_body


def update_frontmatter_field(frontmatter_str: str, key: str, value: str, force: bool = False):
    """更新 frontmatter 字段。返回 (新字符串, 是否实际修改)。"""
    lines = frontmatter_str.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:", line):
            current_val = line.split(":", 1)[1].strip()
            if force:
                if str(current_val) == str(value):
                    return frontmatter_str, False
                lines[i] = f"{key}: {value}"
                return "\n".join(lines), True
            else:
                if not current_val or current_val in ("", "''", '""'):
                    lines[i] = f"{key}: {value}"
                    return "\n".join(lines), True
                return frontmatter_str, False
    lines.append(f"{key}: {value}")
    return "\n".join(lines), True


def wikilink_names_in_section(body_text: str, section_heading: str,
                               known_names: set[str]) -> str:
    """在 body 的指定 ## section 中，将已知人名包裹为 [[name]] wikilink（不重复包裹）。"""
    lines = body_text.splitlines()
    heading = f"## {section_heading}"
    in_section = False
    modified = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if re.match(rf"^##\s+{re.escape(section_heading)}", stripped):
            in_section = True
            new_lines.append(line)
            continue
        if in_section:
            if stripped.startswith("## "):
                in_section = False
                new_lines.append(line)
                continue
            # 对该行中的已知名称做 wikilink 包裹
            new_line = line
            for name in sorted(known_names, key=len, reverse=True):  # 长名优先
                # 避免重复包裹
                pattern = rf"(?<!\[\[){re.escape(name)}(?!\]\])"
                replacement = f"[[{name}]]"
                if re.search(pattern, new_line):
                    new_line = re.sub(pattern, replacement, new_line)
                    modified = True
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    if modified:
        return "\n".join(new_lines)
    return body_text


def build_entity_note(name: str, first_chapter: str,
                       section_heading: str, note_prefix: str = "") -> str:
    """生成新实体笔记模板。"""
    return f"""---
name: {name}
aliases: []
status: alive
first_chapter: {first_chapter}
---

{note_prefix}# {name}

## {section_heading}
- [[{first_chapter}]]
"""


# ===================================================================
#  主逻辑
# ===================================================================

def process_novel(novel_dir: Path, entity_types: list[str], target_chapter: int | None = None):
    """处理单部小说的所有实体类型。"""
    novel_name = novel_dir.name
    chapters_dir = novel_dir / "04_Chapters"

    if not chapters_dir.is_dir():
        log.warning("跳过 '%s'：没有 04_Chapters 目录", novel_name)
        return

    # 扫描章节文件
    all_ch_files = sorted(
        chapters_dir.glob("第*.md"),
        key=lambda p: extract_chapter_number(p.stem) or 0,
    )
    if target_chapter is not None:
        chapter_files = [f for f in all_ch_files if extract_chapter_number(f.stem) == target_chapter]
        if not chapter_files:
            log.warning("跳过 '%s'：未找到第%d章文件", novel_name, target_chapter)
            return
    else:
        chapter_files = all_ch_files
    if not chapter_files:
        log.warning("跳过 '%s'：04_Chapters 下没有 '第*.md' 章节文件", novel_name)
        return

    log.info("=== 处理小说: %s ===", novel_name)

    # ---- 第一遍：收集所有章节的实体出现数据 ----
    chapter_data: list[dict] = []  # [{ch_num, chapter_label, entities: {type: set}}]
    all_new_entities: dict[str, dict[str, str]] = {}  # {type: {name: first_chapter}}
    all_entities_per_type: dict[str, set[str]] = defaultdict(set)

    for chapter_path in chapter_files:
        ch_num = extract_chapter_number(chapter_path.stem)
        if ch_num is None:
            log.warning("  无法提取章节号: %s", chapter_path.name)
            continue

        chapter_label = f"第{ch_num}章"
        text = chapter_path.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        if fm is None:
            log.warning("  [WARN] frontmatter 解析失败: %s", chapter_path.name)
            continue

        entry = {"ch_num": ch_num, "chapter_label": chapter_label, "entities": {}}

        for etype in entity_types:
            cfg = ENTITY_CONFIG[etype]
            involved = fm.get(cfg["fm_field"]) or []
            new_field = cfg.get("new_fm_field")
            raw_list = fm.get(new_field) if new_field else []
            new_list = raw_list if raw_list is not None else []

            if isinstance(involved, str):
                involved = [involved]
            if isinstance(new_list, str):
                new_list = [new_list]

            involved = [n for n in involved if n and isinstance(n, str)]
            new_list = [n for n in new_list if n and isinstance(n, str)]

            entry["entities"][etype] = set(involved)
            all_entities_per_type[etype].update(involved)

            for name in new_list:
                all_new_entities.setdefault(etype, {})[name] = chapter_label

        chapter_data.append(entry)

    # ---- 构建共现关系表 ----
    # co_occurrence[etype][name] = {other_name, ...}
    co_occurrence: dict[str, dict[str, set[str]]] = {
        etype: defaultdict(set) for etype in entity_types
    }
    for entry in chapter_data:
        for etype in entity_types:
            names = entry["entities"].get(etype, set())
            for name in names:
                co_occurrence[etype][name].update(names - {name})

    # ---- 第二遍：创建/更新实体笔记 ----
    for etype in entity_types:
        cfg = ENTITY_CONFIG[etype]
        entity_dir = novel_dir / cfg["dir"]
        entity_dir.mkdir(parents=True, exist_ok=True)

        log.info("  -- 处理 %s --", etype)

        # 汇总该类型在所有章节的出现（用于出现章节列表）
        appearance_map: dict[str, set[str]] = defaultdict(set)
        for entry in chapter_data:
            for name in entry["entities"].get(etype, set()):
                appearance_map[name].add(entry["chapter_label"])

        # 获取已有的实体笔记文件名集合（用于 wikilink 匹配）
        existing_files = {f.stem for f in entity_dir.glob("*.md")}

        for entity_name in sorted(all_entities_per_type.get(etype, set())):
            entity_file = entity_dir / f"{entity_name}.md"
            chapters_present = sorted(appearance_map.get(entity_name, set()),
                                       key=lambda l: extract_chapter_number(l) or 0)
            first_chapter = chapters_present[0] if chapters_present else ""
            is_new_entity = entity_name in all_new_entities.get(etype, {})

            if not entity_file.exists():
                # ---- 创建新笔记 ----
                content = build_entity_note(
                    name=entity_name,
                    first_chapter=first_chapter,
                    section_heading=cfg["section"],
                    note_prefix=cfg.get("note_prefix", ""),
                )
                # 添加共现关系
                if co_occurrence.get(etype, {}).get(entity_name):
                    cocur = sorted(co_occurrence[etype][entity_name],
                                   key=lambda n: extract_chapter_number(
                                       all_new_entities.get(etype, {}).get(n, "")) or 0)
                    if cocur:
                        content = content.rstrip("\n") + "\n\n"
                        content += f"## {cfg['rel_section']}\n"
                        content += "\n".join(f"- [[{n}]]" for n in cocur) + "\n"

                entity_file.write_text(content, encoding="utf-8")
                log.info("    [NEW] 创建: %s", entity_name)
            else:
                # ---- 更新已有笔记 ----
                existing_text = entity_file.read_text(encoding="utf-8")
                existing_fm, existing_body = parse_frontmatter(existing_text)
                modified = False

                # -- 更新 frontmatter --
                fm_raw = re.match(r"^---\s*\n(.*?)\n---", existing_text, re.DOTALL)
                if fm_raw and existing_fm is not None:
                    fm_str = fm_raw.group(1)

                    # first_chapter
                    if is_new_entity:
                        current_first = existing_fm.get("first_chapter", "")
                        if not current_first or str(current_first).strip() in ("", "''", '""'):
                            fm_str, chg = update_frontmatter_field(fm_str, "first_chapter", first_chapter)
                            if chg:
                                modified = True

                    # last_appearance_chapter
                    existing_last = existing_fm.get("last_appearance_chapter", "")
                    if existing_last:
                        try:
                            existing_last_num = int(str(existing_last).strip())
                        except (ValueError, TypeError):
                            existing_last_num = 0
                    else:
                        existing_last_num = 0
                    latest_ch = max(chapters_present, key=lambda l: extract_chapter_number(l) or 0)
                    latest_num = extract_chapter_number(latest_ch) or 0
                    if latest_num > existing_last_num:
                        fm_str, _ = update_frontmatter_field(fm_str, "last_appearance_chapter",
                                                              str(latest_num), force=True)
                        modified = True

                    if modified:
                        existing_text = f"---\n{fm_str}\n---\n{existing_body}"

                # -- 更新出现章节 section --
                existing_ch_links = parse_list_section(existing_body, cfg["section"])
                for cl in chapters_present:
                    if cl not in existing_ch_links:
                        existing_ch_links.add(cl)
                        modified = True
                # 始终重写以保持排序
                sorted_ch = sorted(existing_ch_links,
                                   key=lambda l: extract_chapter_number(l) or 0)
                fm_m = re.match(r"^---\s*\n(.*?)\n---\s*", existing_text, re.DOTALL)
                if fm_m:
                    _, body_tmp = parse_frontmatter(existing_text)
                    new_body = replace_or_append_section(body_tmp, cfg["section"], sorted_ch)
                    existing_text = f"---\n{fm_m.group(1)}\n---\n{new_body}"
                else:
                    existing_text = replace_or_append_section(existing_text, cfg["section"], sorted_ch)

                # -- 生成/更新共现关系 section --
                cocur = sorted(co_occurrence.get(etype, {}).get(entity_name, set()),
                               key=lambda n: extract_chapter_number(
                                   all_new_entities.get(etype, {}).get(n, "")) or 0)
                if cocur:
                    fm_m = re.match(r"^---\s*\n(.*?)\n---\s*", existing_text, re.DOTALL)
                    if fm_m:
                        _, body_tmp = parse_frontmatter(existing_text)
                        new_body = replace_or_append_section(body_tmp, cfg["rel_section"], list(cocur))
                        existing_text = f"---\n{fm_m.group(1)}\n---\n{new_body}"
                    else:
                        existing_text = replace_or_append_section(existing_text, cfg["rel_section"], list(cocur))

                # -- wikilink 已有"人际关系"段落 (仅 character) --
                if etype == "character":
                    all_char_names = all_entities_per_type.get("character", set()) | existing_files
                    fm_m = re.match(r"^---\s*\n(.*?)\n---\s*", existing_text, re.DOTALL)
                    if fm_m:
                        _, body_tmp = parse_frontmatter(existing_text)
                        new_body = wikilink_names_in_section(body_tmp, "人际关系", all_char_names)
                        if new_body != body_tmp:
                            existing_text = f"---\n{fm_m.group(1)}\n---\n{new_body}"
                    else:
                        existing_text = wikilink_names_in_section(existing_text, "人际关系", all_char_names)

                entity_file.write_text(existing_text, encoding="utf-8")
                if modified:
                    log.info("    [UPD] 更新: %s", entity_name)
                else:
                    log.debug("    -- %s 无变化", entity_name)


def main():
    parser = argparse.ArgumentParser(
        description="从章节 frontmatter 构建/更新实体笔记（人物、地点等）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build_characters.py --novel "文明升阶"
  python build_characters.py --novel "文明升阶" --types character,location
  python build_characters.py
        """,
    )
    parser.add_argument("--chapter", type=int, default=None,
                        help="仅处理指定章节（如 --chapter 12）")
    parser.add_argument("--novel", type=str, default=None,
                        help="指定要处理的小说名。不指定则处理所有小说。")
    parser.add_argument("--types", type=str, default="character",
                        help="要处理的实体类型，逗号分隔。可选: %s。默认: character"
                             % ", ".join(ENTITY_CONFIG.keys()))
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 解析 --types
    requested = [t.strip() for t in args.types.split(",") if t.strip() in ENTITY_CONFIG]
    if not requested:
        log.error("无效的 --types 参数。可选: %s", ", ".join(ENTITY_CONFIG.keys()))
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    novels_root = script_dir / "Novels"

    if not novels_root.is_dir():
        log.error("未找到 Novels 目录: %s", novels_root)
        sys.exit(1)

    if args.novel:
        target = novels_root / args.novel
        if not target.is_dir():
            log.error("小说目录不存在: %s", target)
            sys.exit(1)
        process_novel(target, requested, args.chapter)
    else:
        novel_dirs = sorted([d for d in novels_root.iterdir() if d.is_dir()],
                            key=lambda d: d.name)
        if not novel_dirs:
            log.warning("Novels 目录下没有小说子目录。")
            return
        for novel_dir in novel_dirs:
            process_novel(novel_dir, requested, args.chapter)
            print()

    log.info("[OK] 全部完成。")


if __name__ == "__main__":
    main()


