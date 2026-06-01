#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_hooks.py -- 扫描所有章节的"本章元数据"区块，自动更新伏笔追踪表。

功能：
  1. 遍历 04_Chapters/ 下所有章节文件
  2. 从每个文件的 ## 本章元数据 区块中提取：
     - ### 新伏笔/坑 → 新增到追踪表
     - ### 已填旧坑 → 标记对应伏笔为 resolved
  3. 生成/更新 03_Hooks/Hooks_Tracker.md

用法:
    python update_hooks.py --novel "文明升阶"
    python update_hooks.py --novel "文明升阶" --verbose

依赖: PyYAML (pip install pyyaml)
"""

import argparse
import io
import logging
import re
import sys
from pathlib import Path

# ====================================================================
#  依赖检查
# ====================================================================
try:
    import yaml
except ImportError:
    try:
        from ruamel import yaml
    except ImportError:
        print("错误: 缺少 YAML 库。安装: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

# ====================================================================
#  日志
# ====================================================================
class _UTF8StreamHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__(stream=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                                  errors="replace"))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s %(message)s",
    handlers=[_UTF8StreamHandler()],
)
log = logging.getLogger("update_hooks")


# ====================================================================
#  工具函数
# ====================================================================

def extract_chapter_number(label: str) -> int | None:
    m = re.match(r"第(\d+)章", label)
    return int(m.group(1)) if m else None


def extract_metadata_section(text: str) -> dict:
    """从章节文件中提取 ## 本章元数据 区块下的各子段内容。

    返回: {"新伏笔/坑": [desc, ...], "已填旧坑": [desc, ...], ...}
    """
    result: dict[str, list[str]] = {}

    # 定位 ## 本章元数据
    meta_start = re.search(r"\n##\s+本章元数据\s*\n", text)
    if not meta_start:
        return result

    meta_text = text[meta_start.end():]

    # 按 ### 分割子段
    current_key = None
    current_items: list[str] = []

    for line in meta_text.splitlines():
        m = re.match(r"^###\s+(.+)", line.strip())
        if m:
            # 保存上一个子段
            if current_key:
                result[current_key] = current_items
            current_key = m.group(1).strip()
            current_items = []
        elif line.strip().startswith("- ") and current_key:
            item = line.strip()[2:].strip()
            if item and item != "无":
                current_items.append(item)

    # 最后一个子段
    if current_key:
        result[current_key] = current_items

    return result


def parse_existing_hooks(text: str) -> tuple[list[dict], int]:
    """解析现有 Hooks_Tracker.md 中的表格。

    返回 (hooks_list, next_id_num)
    每个 hook: {id, description, planted_chapter, plan_chapter, status}
    """
    hooks: list[dict] = []
    max_id = 0

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| H-"):
            continue
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cols) < 5:
            continue
        hid = cols[0].strip()
        desc = cols[1].strip()
        planted = cols[2].strip() if len(cols) > 2 else ""
        plan = cols[3].strip() if len(cols) > 3 else ""
        status = cols[4].strip() if len(cols) > 4 else ""

        hooks.append({
            "id": hid,
            "description": desc,
            "planted_chapter": planted,
            "plan_chapter": plan,
            "status": status,
        })

        # 提取 H-NNN 中的数字
        num_match = re.match(r"H-(\d+)", hid)
        if num_match:
            max_id = max(max_id, int(num_match.group(1)))

    return hooks, max_id + 1


def generate_hook_id(next_id: int) -> str:
    """生成新伏笔 ID，格式 H-001。"""
    return f"H-{next_id:03d}"


def fuzzy_match_resolved(hook_desc: str, existing_hooks: list[dict]) -> list[str]:
    """将"已填旧坑"描述与现有伏笔进行模糊匹配，返回匹配到的伏笔 ID 列表。

    匹配策略（按优先级）:
    1. 精确子串：已填描述包含伏笔描述，或反之
    2. 提取"核心关键词"（冒号/破折号前的部分）进行匹配
    3. 关键词重叠度 >= 30%
    """
    matched_ids: list[str] = []
    # 提取核心关键词（冒号/：/-/—— 之前的部分）
    core = re.split(r"[：:——\-–]", hook_desc)[0].strip()
    core_words = set(re.findall(r"[\u4e00-\u9fff\w]+", core))
    full_words = set(re.findall(r"[\u4e00-\u9fff\w]+", hook_desc))

    for hook in existing_hooks:
        if hook["status"].startswith("resolved"):
            continue
        hook_core = re.split(r"[：:——\-–]", hook["description"])[0].strip()
        hook_words = set(re.findall(r"[\u4e00-\u9fff\w]+", hook["description"]))

        # 1. 包含关系
        if hook["description"] in hook_desc or hook_desc in hook["description"]:
            matched_ids.append(hook["id"])
            continue
        # 核心词包含
        if hook_core and core and (hook_core in core or core in hook_core):
            matched_ids.append(hook["id"])
            continue

        # 2. 核心关键词重叠（只比较核心部分）
        if core_words and hook_words:
            overlap_core = len(core_words & hook_words)
            min_core = min(len(core_words), len(hook_words))
            if min_core > 0 and overlap_core / min_core >= 0.5:
                matched_ids.append(hook["id"])
                continue

        # 3. 全文关键词重叠 >= 30%
        if full_words and hook_words:
            overlap = len(full_words & hook_words)
            min_len = min(len(full_words), len(hook_words))
            if min_len > 0 and overlap / min_len >= 0.3:
                matched_ids.append(hook["id"])

    return matched_ids


def build_tracker_markdown(hooks: list[dict], frontmatter_text: str) -> str:
    """根据 hooks 列表生成完整的 Hooks_Tracker.md 内容。"""
    lines: list[str] = []
    lines.append(frontmatter_text.strip())
    lines.append("")
    lines.append("# 伏笔追踪表")
    lines.append("")
    lines.append("| ID | 描述 | 埋坑章节 | 计划填坑 | 状态 |")
    lines.append("|----|------|----------|----------|------|")

    for hook in hooks:
        lines.append(
            f"| {hook['id']} | {hook['description']} "
            f"| {hook['planted_chapter']} | {hook['plan_chapter']} "
            f"| {hook['status']} |"
        )

    lines.append("")
    lines.append("## 状态说明")
    lines.append("- **unresolved**: 已埋，尚未填坑")
    lines.append("- **partial**: 部分回收（信息已更新但尚未完全闭合）")
    lines.append("- **resolved**: 已填坑")
    lines.append("")

    return "\n".join(lines)


# ====================================================================
#  主流程
# ====================================================================

def update_hooks(novel_dir: Path, target_chapter: int | None = None):
    novel_name = novel_dir.name
    chapters_dir = novel_dir / "04_Chapters"
    hooks_dir = novel_dir / "03_Hooks"
    tracker_file = hooks_dir / "Hooks_Tracker.md"

    log.info("=" * 50)
    log.info("  更新伏笔追踪: %s", novel_name)
    log.info("=" * 50)

    if not chapters_dir.is_dir():
        log.error("[ERROR] 未找到 04_Chapters 目录")
        return

    # 扫描章节文件
    all_cf = sorted(
        [(extract_chapter_number(f.stem), f)
         for f in chapters_dir.glob("第*.md") if extract_chapter_number(f.stem)],
        key=lambda x: x[0],
    )
    if target_chapter is not None:
        chapter_files = [(n, f) for n, f in all_cf if n == target_chapter]
        if not chapter_files:
            log.warning("未找到第%d章文件，跳过", target_chapter)
            return
    else:
        chapter_files = all_cf
    if not chapter_files:
        log.warning("[WARN] 没有章节文件")
        return

    log.info("  扫描 %d 个章节", len(chapter_files))

    # 加载现有追踪表
    hooks_dir.mkdir(parents=True, exist_ok=True)
    existing_frontmatter = f"---\ntype: foreshadowing\nnovel: \"{novel_name}\"\ntitle: \"伏笔追踪表\"\ncreated: 2026-05-30\nupdated: 2026-05-30\n---"
    existing_hooks: list[dict] = []
    next_id = 1

    if tracker_file.is_file():
        tracker_text = tracker_file.read_text(encoding="utf-8")
        # 提取现有 frontmatter
        fm_match = re.match(r"^---\s*\n.*?\n---", tracker_text, re.DOTALL)
        if fm_match:
            existing_frontmatter = fm_match.group(0)
        existing_hooks, next_id = parse_existing_hooks(tracker_text)
        log.info("  现有伏笔: %d 条 (下一个 ID: H-%03d)", len(existing_hooks), next_id)
    else:
        log.info("  新建追踪表")

    # 扫描所有章节，收集新伏笔和已填标记
    new_hooks_total = 0
    resolved_total = 0
    unresolved_resolved = 0

    for ch_num, ch_path in chapter_files:
        chapter_label = f"第{ch_num}章"
        text = ch_path.read_text(encoding="utf-8")
        metadata = extract_metadata_section(text)

        new_hooks = metadata.get("新伏笔/坑", [])
        resolved_hooks = metadata.get("已填旧坑", [])

        # 处理新伏笔
        for desc in new_hooks:
            # 与所有已有伏笔做去重（不限章节）
            already_exists = any(
                _hook_overlaps_with(h["description"], desc)
                for h in existing_hooks
            )
            if not already_exists:
                hook_id = generate_hook_id(next_id)
                existing_hooks.append({
                    "id": hook_id,
                    "description": desc,
                    "planted_chapter": chapter_label,
                    "plan_chapter": "",
                    "status": "unresolved",
                })
                next_id += 1
                new_hooks_total += 1
                log.info("  [NEW] %s | %s | %s", hook_id, chapter_label, desc[:50])

        # 处理已填旧坑
        for desc in resolved_hooks:
            matched = fuzzy_match_resolved(desc, existing_hooks)
            if matched:
                for hid in matched:
                    for h in existing_hooks:
                        if h["id"] == hid and not h["status"].startswith("resolved"):
                            h["status"] = f"resolved (第{ch_num}章)"
                            resolved_total += 1
                            log.info("  [RESOLVED] %s → %s | %s", hid, chapter_label, desc[:50])
            else:
                # 没匹配到已有伏笔，可能是手动描述的填坑，也记录
                log.warning("  [MANUAL] 需人工匹配已填旧坑: %s", desc[:50])

    # 写入
    tracker_md = build_tracker_markdown(existing_hooks, existing_frontmatter)
    tracker_file.write_text(tracker_md, encoding="utf-8")
    if unresolved_resolved > 0:
        log.warning("  [MANUAL] %d 条已填旧坑无法自动匹配，请手动更新", unresolved_resolved)
    log.info("  [OK] 已写入: %s", tracker_file)
    log.info("  新增: %d | 填坑: %d | 总计: %d", new_hooks_total, resolved_total, len(existing_hooks))
    log.info("=" * 50)


def _hook_overlaps_with(existing_desc: str, new_desc: str) -> bool:
    """判断新伏笔描述是否与已有伏笔高度重叠（应视为重复）。"""
    # 提取核心部分（冒号前）
    e_core = re.split(r"[：:——\-–]", existing_desc)[0].strip()
    n_core = re.split(r"[：:——\-–]", new_desc)[0].strip()
    e_words = set(re.findall(r"[\u4e00-\u9fff\w]+", existing_desc))
    n_words = set(re.findall(r"[\u4e00-\u9fff\w]+", new_desc))

    # 核心包含
    if e_core and n_core and (e_core in n_core or n_core in e_core):
        return True
    # 核心关键词重叠 >= 50%
    e_core_words = set(re.findall(r"[\u4e00-\u9fff\w]+", e_core))
    n_core_words = set(re.findall(r"[\u4e00-\u9fff\w]+", n_core))
    if e_core_words and n_core_words:
        overlap = len(e_core_words & n_core_words)
        min_len = min(len(e_core_words), len(n_core_words))
        if overlap / min_len >= 0.5:
            return True
    # 全文重叠 >= 40%
    if e_words and n_words:
        overlap = len(e_words & n_words)
        min_len = min(len(e_words), len(n_words))
        if overlap / min_len >= 0.4:
            return True
    return False


def _descs_similar(a: str, b: str) -> bool:
    """简单判断两个描述是否指向同一件事。"""
    a_words = set(re.findall(r"[\u4e00-\u9fff\w]+", a))
    b_words = set(re.findall(r"[\u4e00-\u9fff\w]+", b))
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words)
    min_len = min(len(a_words), len(b_words))
    return overlap / min_len >= 0.3 if min_len > 0 else False


# ====================================================================
#  CLI
# ====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="扫描章节元数据，自动更新伏笔追踪表",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python update_hooks.py --novel "文明升阶"
  python update_hooks.py --novel "文明升阶" --verbose
        """,
    )
    parser.add_argument("--chapter", type=int, default=None,
                        help="仅处理指定章节（如 --chapter 12）")
    parser.add_argument("--novel", type=str, required=True, help="小说文件夹名（必填）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    script_dir = Path(__file__).resolve().parent
    novels_root = script_dir / "Novels"
    if not novels_root.is_dir():
        log.error("[ERROR] 未找到 Novels 目录: %s", novels_root)
        sys.exit(1)

    target = novels_root / args.novel
    if not target.is_dir():
        log.error("[ERROR] 小说目录不存在: %s", target)
        sys.exit(1)

    update_hooks(target, args.chapter)
    log.info("[OK] 全部完成。")


if __name__ == "__main__":
    main()



