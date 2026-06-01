#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_context.py -- 为长篇小说自动生成"当前写作上下文"（Current_Context.md）。

功能：
  1. 从 核心框架.md 提取"世界观基石"+"写作规则"，作为长期核心规则
  2. 扫描最近 N 章，提取摘要
  3. 从人物笔记提取活跃人物
  4. 从伏笔追踪表提取即将到期的待填坑
  5. 提取世界观核心 + 上一章结尾段落

用法:
    python build_context.py --novel "文明升阶"
    python build_context.py --novel "文明升阶" --last 5

依赖: PyYAML (pip install pyyaml)
"""

import argparse
import io
import logging
import re
import sys
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
# 日志（Windows GBK → UTF-8 包装）
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
log = logging.getLogger("build_context")


# ===================================================================
#  工具函数
# ===================================================================

def parse_frontmatter(text: str):
    """解析 YAML frontmatter → (dict|None, body)"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None, text
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, text
    return (data if isinstance(data, dict) else None, text[m.end():])


def extract_chapter_number(label: str) -> int | None:
    """'第N章' / '第N章 标题' → int(N)"""
    m = re.match(r"第(\d+)章", label)
    return int(m.group(1)) if m else None


def extract_md_section(text: str, heading: str) -> str | None:
    """提取 ## heading 下的全部内容（从 heading 行到下一个 ## 或 EOF）。
    保留原 Markdown 格式。"""
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            start = i
            break
    if start is None:
        return None

    # 收集从下一行起的内容，直到下一个 ## 或 EOF
    content_lines = []
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s", lines[j]):
            break
        content_lines.append(lines[j])

    return "\n".join(content_lines).strip()


def extract_last_narrative_paragraph(text: str) -> str:
    """提取章节正文最后一两段叙事文字（跳过 ## 小结段落）。"""
    # 找到 "## 本章小结" 或第一个 ## 标题之前的内容区域
    body_end = re.search(r"\n##\s+本章小结", text)
    if not body_end:
        body_end = re.search(r"\n##\s", text)
    if body_end:
        text = text[:body_end.start()]

    # 去掉 frontmatter
    _, body = parse_frontmatter(text)
    if body is None:
        body = text

    # 去掉开头的 # 标题行
    body = re.sub(r"^#\s+.+\n", "", body).strip()

    # 按空行分割，取最后 1~2 个非空段落
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        return ""

    # 取最后 2 段或 1 段（不超过 300 字）
    result_parts = []
    total_len = 0
    for p in reversed(paragraphs):
        if total_len + len(p) > 300 and result_parts:
            break
        result_parts.insert(0, p)
        total_len += len(p)
        if len(result_parts) >= 2:
            break

    return "\n\n".join(result_parts)


def parse_hooks_table(text: str, max_chapter: int) -> list[dict]:
    """解析 Hooks_Tracker.md 的 Markdown 表格，筛选即将到期的未填伏笔。

    返回 [{id, description, plan_chapter, status}, ...]
    筛选条件：status == 'unresolved' 且 plan_chapter 在 [max_chapter-2, max_chapter+5] 范围内
    """
    # 找表格行（以 | 开头的行，跳过表头分隔行）
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # 跳过分隔行（如 |---|---|）
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cols) >= 4:
            rows.append(cols)

    if not rows:
        return []

    result = []
    for cols in rows:
        if len(cols) < 5:
            continue
        hid = cols[0].strip()
        desc = cols[1].strip()
        plan_chapter_raw = cols[3].strip()
        status = cols[4].strip().lower() if len(cols) > 4 else ""

        # 只取 unresolved
        if status != "unresolved":
            continue

        # 提取计划填坑的章节号
        plan_nums = [int(m) for m in re.findall(r"第(\d+)章", plan_chapter_raw)]
        if not plan_nums:
            # 尝试匹配 "第四卷" 等 → 视为远期，跳过
            if re.search(r"第[一二三四五六七八九]卷|全书|后续", plan_chapter_raw):
                continue
            # 无法提取数字 → 跳过
            continue
        plan_ch = max(plan_nums)

        # 筛选范围：max_chapter-2 <= plan_ch <= max_chapter+5
        if plan_ch >= max_chapter and plan_ch <= max_chapter + 5:
            result.append({
                "id": hid,
                "description": desc,
                "plan_chapter": plan_ch,
            })

    # 按计划章节号排序
    result.sort(key=lambda x: x["plan_chapter"])
    return result


def extract_long_term_rules(framework_path: Path) -> str | None:
    """从 核心框架.md 提取 ## 世界观基石 和 ## 写作规则 内容。
    返回 Markdown 文本，或 None（文件不存在时）。"""
    if not framework_path.is_file():
        log.warning("  [WARN] 核心框架.md 不存在: %s", framework_path)
        return None

    text = framework_path.read_text(encoding="utf-8")

    # 注意：核心框架.md 中可能用 "## 1. 世界观基石" 或 "## 世界观基石"
    # 写作规则可能是 "## 5. 写作规则"
    worldview_section = None
    rules_section = None

    for pattern, heading in [
        (r"^##\s+\d*[.\s]*世界观基石\s*$", "世界观基石"),
        (r"^##\s+\d*[.\s]*写作规则.*$", "写作规则"),
    ]:
        lines = text.splitlines()
        start = None
        for i, line in enumerate(lines):
            if re.match(pattern, line.strip()):
                start = i
                break
        if start is None:
            continue

        content_lines = []
        for j in range(start + 1, len(lines)):
            if re.match(r"^##\s", lines[j]):
                break
            content_lines.append(lines[j])
        section_text = "\n".join(content_lines).strip()

        if "世界观基石" in heading:
            worldview_section = section_text
        elif "写作规则" in heading:
            rules_section = section_text

    if not worldview_section and not rules_section:
        log.warning("  [WARN] 核心框架.md 中未找到'世界观基石'或'写作规则'章节")
        return None

    # 组装输出
    parts = []
    if worldview_section:
        parts.append(f"### 世界观基石\n\n{worldview_section}")
    if rules_section:
        parts.append(f"### 写作规则\n\n{rules_section}")

    return "\n\n".join(parts)


# ===================================================================
#  主逻辑
# ===================================================================

def build_context(novel_dir: Path, last_n: int, target_chapter: int | None = None):
    """为一本小说生成 Current_Context.md。"""
    novel_name = novel_dir.name

    chapters_dir = novel_dir / "04_Chapters"
    characters_dir = novel_dir / "01_Characters"
    hooks_file = novel_dir / "03_Hooks" / "Hooks_Tracker.md"
    worldview_file = novel_dir / "00_Worldview" / "Main_Worldview.md"
    framework_file = novel_dir / "核心框架.md"
    context_dir = novel_dir / "05_Context"
    context_file = context_dir / "Current_Context.md"

    # 必须的目录检查
    if not chapters_dir.is_dir():
        log.warning("跳过 '%s'：没有 04_Chapters 目录", novel_name)
        return

    # ---- 扫描章节 ----
    all_ch_files = sorted(
        chapters_dir.glob("第*.md"),
        key=lambda p: extract_chapter_number(p.stem) or 0,
    )
    if target_chapter is not None:
        chapter_files = [f for f in all_ch_files if extract_chapter_number(f.stem) == target_chapter]
        if not chapter_files:
            log.warning("未找到第%d章文件，跳过", target_chapter)
            return
    else:
        chapter_files = all_ch_files
    if not chapter_files:
        log.warning("跳过 '%s'：没有章节文件", novel_name)
        return

    all_chapters = []
    for cf in chapter_files:
        n = extract_chapter_number(cf.stem)
        if n:
            all_chapters.append((n, cf))

    if not all_chapters:
        log.warning("跳过 '%s'：无法解析章节号", novel_name)
        return

    max_chapter = max(n for n, _ in all_chapters)
    log.info("=== 处理小说: %s（共 %d 章）===", novel_name, max_chapter)

    # 最近 N 章
    recent_chapters = all_chapters[-last_n:] if len(all_chapters) >= last_n else all_chapters
    log.info("  最近 %d 章: %s", len(recent_chapters),
             ", ".join(f"第{n}章" for n, _ in recent_chapters))

    # ---- 1. 长期核心规则 ----
    long_term_rules = extract_long_term_rules(framework_file)

    # ---- 2. 最近剧情摘要 ----
    summaries = []
    for ch_num, ch_path in recent_chapters:
        text = ch_path.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        if fm and fm.get("summary"):
            summaries.append((ch_num, fm["summary"]))
        else:
            # 取正文前 200 字符
            _, body = parse_frontmatter(text)
            if body:
                body_clean = re.sub(r"^#\s+.+\n", "", body).strip()
                snippet = body_clean[:200].replace("\n", " ")
                summaries.append((ch_num, snippet + "…"))
            else:
                summaries.append((ch_num, "（无摘要）"))

    # ---- 3. 活跃人物 ----
    active_characters = []
    if characters_dir.is_dir():
        for char_file in sorted(characters_dir.glob("*.md")):
            text = char_file.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            if not fm:
                continue
            last_ch = fm.get("last_appearance_chapter", "")
            if last_ch == "" or last_ch is None:
                continue
            try:
                last_ch_num = int(str(last_ch).strip())
            except (ValueError, TypeError):
                continue

            # 最后 20 章内出现的视为活跃
            if last_ch_num >= max_chapter - 20:
                name = fm.get("name") or char_file.stem
                status = fm.get("status", "未知")
                status_cn = {"alive": "存活", "dead": "已故", "unknown": "未知"}.get(
                    str(status).strip().lower(), str(status))
                active_characters.append((name, status_cn, last_ch_num))

    # 去重（按 name）
    seen_names = set()
    deduped = []
    for item in active_characters:
        if item[0] not in seen_names:
            seen_names.add(item[0])
            deduped.append(item)
    active_characters = deduped
    active_characters.sort(key=lambda x: x[2], reverse=True)

    # ---- 4. 即将到期的伏笔 ----
    upcoming_hooks = []
    if hooks_file.is_file():
        hooks_text = hooks_file.read_text(encoding="utf-8")
        upcoming_hooks = parse_hooks_table(hooks_text, max_chapter)

    # ---- 5. 世界观核心 ----
    worldview_short = ""
    if worldview_file.is_file():
        wv_text = worldview_file.read_text(encoding="utf-8")
        _, wv_body = parse_frontmatter(wv_text)
        if wv_body:
            # 取前 10 行（跳过标题行）
            lines = [l for l in wv_body.splitlines() if l.strip() and not l.strip().startswith("# ")]
            worldview_short = "\n".join(lines[:10])

    # ---- 6. 上一章结尾 ----
    last_chapter_end = ""
    if all_chapters:
        _, last_ch_path = all_chapters[-1]
        last_text = last_ch_path.read_text(encoding="utf-8")
        last_chapter_end = extract_last_narrative_paragraph(last_text)

    # ---- 生成输出 ----
    context_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("---")
    lines.append(f"type: context")
    lines.append(f'novel: "{novel_name}"')
    lines.append(f"title: \"当前写作上下文\"")
    last_ch_label = f"第{all_chapters[-1][0]}章" if all_chapters else ""
    lines.append(f"last_chapter: \"{last_ch_label}\"")
    lines.append(f"next_chapter: \"\"")
    lines.append(f"created: 2026-05-30")
    lines.append(f"updated: 2026-05-30")
    lines.append("---")
    lines.append("")
    lines.append("# 当前写作上下文")
    lines.append("")

    # --- 长期核心规则 ---
    if long_term_rules:
        lines.append("## 长期核心规则（必须遵守）")
        lines.append("")
        lines.append(long_term_rules)
        lines.append("")

    # --- 最近剧情摘要 ---
    lines.append("## 最近剧情摘要")
    for ch_num, summary in summaries:
        lines.append(f"- 第{ch_num}章：{summary}")
    lines.append("")

    # --- 当前活跃人物 ---
    lines.append("## 当前活跃人物")
    if active_characters:
        for name, status, last_ch in active_characters:
            lines.append(f"- {name}（{status}，最后出现于第{last_ch}章）")
    else:
        lines.append("（无活跃人物数据）")
    lines.append("")

    # --- 即将到期的伏笔 ---
    lines.append("## 即将到期的伏笔（需关注）")
    if upcoming_hooks:
        for hook in upcoming_hooks:
            lines.append(f"- [ ] {hook['description']}（计划第{hook['plan_chapter']}章填）")
    else:
        lines.append("（暂无即将到期的伏笔）")
    lines.append("")

    # --- 世界观核心规则 ---
    lines.append("## 世界观核心规则")
    lines.append(worldview_short if worldview_short else "（暂无）")
    lines.append("")

    # --- 上一章结尾 ---
    lines.append("## 上一章结尾")
    lines.append(last_chapter_end if last_chapter_end else "（无）")
    lines.append("")

    # --- 本章写作目标 ---
    lines.append("## 本章写作目标（请用户填写）")
    lines.append("（在此填写本章的写作目标和关键情节要点）")
    lines.append("")

    output = "\n".join(lines)
    context_file.write_text(output, encoding="utf-8")
    log.info("  [OK] 已生成: %s", context_file)


def main():
    parser = argparse.ArgumentParser(
        description="生成长篇小说写作上下文（Current_Context.md）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build_context.py --novel "文明升阶"
  python build_context.py --novel "文明升阶" --last 5
        """,
    )
    parser.add_argument("--chapter", type=int, default=None,
                        help="仅处理指定章节（如 --chapter 12）")
    parser.add_argument("--novel", type=str, default=None,
                        help="指定要处理的小说名。不指定则处理所有小说。")
    parser.add_argument("--last", type=int, default=3,
                        help="参考最近 N 章（默认 3）")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

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
        build_context(target, args.last, args.chapter)
    else:
        novel_dirs = sorted(
            [d for d in novels_root.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )
        if not novel_dirs:
            log.warning("Novels 目录下没有小说子目录。")
            return
        for novel_dir in novel_dirs:
            build_context(novel_dir, args.last, args.chapter)
            print()

    log.info("[OK] 全部完成。")


if __name__ == "__main__":
    main()

