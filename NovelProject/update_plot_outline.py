#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_plot_outline.py -- 更新 Plot_Outline.md 中指定章节的标题。

在表格中将对应章的标题更新/插入到正确位置（按章号排序）。
支持表格和列表两种格式。

用法:
    python update_plot_outline.py --novel "文明升阶" --chapter 16 --title "星海独白"
"""

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def detect_format(lines: list[str]) -> str:
    """检测文件格式：table / list / unknown。"""
    for line in lines:
        if re.search(r"\|\s*章\s*\|", line) or re.search(r"\|\s*章节\s*\|", line):
            return "table"
    for line in lines:
        if re.match(r"^\|\s*\d+\s*\|", line.strip()):
            return "table"
    for line in lines:
        if re.match(r"-\s*第\d+章", line.strip()):
            return "list"
    return "unknown"


def update_table(lines: list[str], chapter: int, title: str, full_line: str | None = None) -> list[str]:
    """表格格式：更新已存在的行，或按章号插入到正确位置。

    表格格式（8列）：| 卷 | 章 | 标题 | 核心事件 | POV | 新增人物 | 埋坑 | 字数预估 |
    新行插入时，第2列（章号）对齐 = 关键排序依据。
    """
    # 找到表头分隔行，确定表格数据起始点
    header_end = -1
    for i, line in enumerate(lines):
        if re.match(r"^\|[\s\-:|]+\|$", line.strip()):
            header_end = i
            break

    if header_end < 0:
        # 没有找到分隔行，当作空表处理
        lines.append("| 卷 | 章 | 标题 | 核心事件 | POV | 新增人物 | 埋坑 | 字数预估 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        header_end = len(lines) - 1

    data_start = header_end + 1

    # 收集表头前的内容 + 表头
    result = lines[:data_start]

    # 解析数据行区域（连续 | 开头的行）
    parsed = []  # [(chapter_num, full_line)]
    after_table_lines = []
    in_table = True
    for i in range(data_start, len(lines)):
        stripped = lines[i].strip()
        if in_table and stripped.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", stripped):
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) >= 2:
                # 尝试从第1列（章号列）中识别章节号，第0列是卷号
                ch = None
                for col_idx in (1, 0):
                    try:
                        val = int(cols[col_idx])
                        if 1 <= val <= 9999:
                            ch = val
                            break
                    except (ValueError, IndexError):
                        continue
                if ch is not None:
                    parsed.append((ch, lines[i]))
                    continue
        in_table = False
        after_table_lines.append(lines[i])

    # 更新或插入
    updated = False
    for j, (ch, line) in enumerate(parsed):
        if ch == chapter:
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 3:
                # 标题在第3列（索引2），索引0=卷，索引1=章
                cols[2] = title
                new_line = "| " + " | ".join(cols) + " |"
            elif len(cols) >= 2:
                cols[1] = title
                new_line = "| " + " | ".join(cols) + " |"
            else:
                if full_line:
                    new_line = full_line
                else:
                    new_line = f"| 1   | {chapter:<4} | {title:<20} | 待写 | 待定 | 无 | 待定 | 待定 |"
            parsed[j] = (ch, new_line)
            updated = True
            break

    if not updated:
        if full_line:
            new_line = full_line
        else:
            new_line = f"| 1   | {chapter:<4} | {title:<20} | 待写 | 待定 | 无 | 待定 | 待定 |"
        parsed.append((chapter, new_line))

    # 按章号排序
    parsed.sort(key=lambda x: x[0])

    result.extend(line for _, line in parsed)
    result.extend(after_table_lines)
    return result
def update_list(lines: list[str], chapter: int, title: str, full_line: str | None = None) -> list[str]:
    """列表格式：查找 '- 第X章：' 行更新，否则按章号插入。"""
    found = False
    pattern = re.compile(rf"^-\s*第{chapter}章\s*[：:]\s*")

    for i, line in enumerate(lines):
        if pattern.match(line.strip()):
            lines[i] = f"- 第{chapter}章：{title}"
            found = True
            break

    if not found:
        new_line = f"- 第{chapter}章：{title}"
        # 按章号找到插入位置
        inserted = False
        for i, line in enumerate(lines):
            m = re.match(r"- 第(\d+)章", line.strip())
            if m and int(m.group(1)) > chapter:
                lines.insert(i, new_line)
                inserted = True
                break
        if not inserted:
            lines.append(new_line)

    return lines


def update_hooks_table(lines: list[str], hooks_text: str) -> list[str]:
    """在“伏笔填坑规划”表格中追加新的伏笔行。"""
    # 找到伏笔填坑规划表格
    in_hooks_section = False
    hooks_table_start = -1
    for i, line in enumerate(lines):
        if re.match(r'^##\s+伏笔填坑规划', line.strip()):
            in_hooks_section = True
            continue
        if in_hooks_section and line.strip().startswith('|'):
            hooks_table_start = i
            break

    if hooks_table_start < 0:
        # 没有伏笔表格，创建
        # 先找到“章节规划表”之后的位置
        for i, line in enumerate(lines):
            if re.match(r'^##\s+伏笔填坑规划', line.strip()):
                lines.insert(i + 1, '')
                lines.insert(i + 2, '| 伏笔 | 埋下章节 | 计划填坑章节 | 说明 |')
                lines.insert(i + 3, '|------|----------|--------------|------|')
                hooks_table_start = i + 2
                break
        else:
            # 完全没有这个section，在末尾追加
            lines.append('')
            lines.append('## 伏笔填坑规划')
            lines.append('')
            lines.append('| 伏笔 | 埋下章节 | 计划填坑章节 | 说明 |')
            lines.append('|------|----------|--------------|------|')
            hooks_table_start = len(lines) - 2

    # 解析已有伏笔行，找到最后一个表格行
    last_table_line = hooks_table_start
    for i in range(hooks_table_start, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith('|') and not re.match(r'^\|[\s\-:|]+\|$', stripped):
            last_table_line = i
        elif not stripped.startswith('|') and i > hooks_table_start + 1:
            break

    # 解析 hooks_text 中的新伏笔行
    new_hook_lines = []
    for line in hooks_text.strip().splitlines():
        stripped = line.strip()
        # 跳过表头和分隔行
        if re.match(r'^\|[\s\-:|]+\|$', stripped):
            continue
        if stripped.startswith('|') and ('伏笔' in stripped or '---' in stripped or ':-' in stripped):
            continue
        if stripped.startswith('|'):
            new_hook_lines.append(line)
        elif stripped.startswith('-') or stripped.startswith('*'):
            # 列表格式的伏笔
            desc = re.sub(r'^[-*]\s*', '', stripped)
            new_hook_lines.append(f'| {desc} | | | |')
        elif stripped and stripped != '无':
            new_hook_lines.append(f'| {stripped} | | | |')

    # 插入新行
    insert_pos = last_table_line + 1
    for hook_line in new_hook_lines:
        lines.insert(insert_pos, hook_line)
        insert_pos += 1

    if new_hook_lines:
        print(f'  伏笔规划: +{len(new_hook_lines)} 条')

    return lines


def update_continuity_section(lines: list[str], chapter: int, continuity_text: str) -> list[str]:
    """更新“已写章节与后续衔接说明”区块。"""
    # 找到该section
    section_start = -1
    for i, line in enumerate(lines):
        if re.match(r'^##\s+已写章节与后续衔接说明', line.strip()):
            section_start = i
            break

    if section_start < 0:
        # 在文件末尾创建
        lines.append('')
        lines.append('## 已写章节与后续衔接说明')
        lines.append('')
        section_start = len(lines) - 1

    # 检查是否已有本章的衔接说明
    pattern = re.compile(rf'- \*\*第{chapter}章.*?\*\*')
    for i in range(section_start, len(lines)):
        if pattern.search(lines[i]):
            # 已有，替换
            lines[i] = continuity_text.strip()
            print(f'  衔接说明: 已更新第{chapter}章')
            return lines

    # 没有，追加到section末尾
    # 找到最后一个非空行
    insert_at = len(lines)
    lines.append(continuity_text.strip())
    # 确保前面有空行
    if lines[-2].strip() != '':
        lines.insert(-1, '')
    print(f'  衔接说明: 已添加第{chapter}章')

    return lines

def update_outline(novel: str, chapter: int, title: str, full_line: str | None = None,
                    hooks: str | None = None, continuity: str | None = None):
    plot_dir = SCRIPT_DIR / "Novels" / novel / "02_Plot"
    plot_dir.mkdir(parents=True, exist_ok=True)
    outline_file = plot_dir / "Plot_Outline.md"

    if outline_file.is_file():
        content = outline_file.read_text(encoding="utf-8")
        lines = content.splitlines()
    else:
        lines = ["| 章节 | 标题 | 状态 |", "|------|------|------|"]

    fmt = detect_format(lines)

    if fmt == "table":
        lines = update_table(lines, chapter, title, full_line)
    else:
        lines = update_list(lines, chapter, title, full_line)

    # 更新伏笔填坑规划
    if hooks and hooks != "无":
        lines = update_hooks_table(lines, hooks)
    # 更新已写章节与后续衔接说明
    if continuity:
        lines = update_continuity_section(lines, chapter, continuity)

    outline_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已更新第{chapter}章标题为：{title}")


def main():
    parser = argparse.ArgumentParser(description="更新 Plot_Outline.md 中章节标题（按章号排序插入）")
    parser.add_argument("--line", type=str, default=None, help="完整表格行（可选）")
    parser.add_argument("--hooks", type=str, default=None, help="新增伏笔表格行（可选）")
    parser.add_argument("--continuity", type=str, default=None, help="衔接说明文本（可选）")
    parser.add_argument("--novel", type=str, required=True, help="小说名（必填）")
    parser.add_argument("--chapter", type=int, required=True, help="章节号（必填）")
    parser.add_argument("--title", type=str, required=True, help="章节标题（必填）")
    args = parser.parse_args()

    try:
        update_outline(args.novel, args.chapter, args.title, args.line,
                       args.hooks, args.continuity)
    except (OSError, IOError) as e:
        print(f"[ERROR] 文件操作失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
