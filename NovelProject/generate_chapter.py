#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_chapter.py -- 增强版章节生成器。

能力：
  1. 从规划表读取标题，无标题时让 AI 自拟
  2. subprocess 调用 analyze_scene_type.py 分析上一章
  3. 内部小说要素规划（节奏、冲突类型、POV 等）
  4. 构造增强提示词（含要素自检清单）
  5. 连续性保障（上章结尾500字 + 情绪基调）
  6. 调用 DeepSeek API 生成完整章节
  7. 保存后自动调用 update_plot_outline.py 更新规划表

用法:
    python generate_chapter.py --novel "文明升阶"
    python generate_chapter.py --novel "文明升阶" --goal "解锁核聚变方案"
    python generate_chapter.py --novel "文明升阶" --chapter 16 --goal "..."

环境变量 / .env: DEEPSEEK_API_KEY
依赖: requests, PyYAML (pip install requests pyyaml)
"""

import argparse
import io
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

# ====================================================================
#  依赖检查
# ====================================================================
try:
    import requests
except ImportError:
    print("错误: 缺少 requests。安装: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    try:
        from ruamel import yaml
    except ImportError:
        print("错误: 缺少 YAML 库。安装: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

# ====================================================================
#  环境变量
# ====================================================================
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.is_file():
    with open(_ENV_FILE, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip().strip("'").strip('"')
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

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
log = logging.getLogger("gen_chapter")

SCRIPT_DIR = Path(__file__).resolve().parent


# ====================================================================
#  基础工具
# ====================================================================

def parse_frontmatter(text: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None, text
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, text
    return (data if isinstance(data, dict) else None, text[m.end():])


def extract_chapter_number(label: str) -> int | None:
    m = re.match(r"第(\d+)章", label)
    return int(m.group(1)) if m else None


def get_chapter_files(chapters_dir: Path) -> list[tuple[int, Path]]:
    result = [(extract_chapter_number(f.stem), f)
              for f in chapters_dir.glob("第*.md") if extract_chapter_number(f.stem)]
    return sorted(result, key=lambda x: x[0])


# ====================================================================
#  规划表标题解析
# ====================================================================

def get_title_from_plot(plot_dir: Path, chapter_num: int) -> str | None:
    """从 Plot_Outline.md 解析章节标题。支持表格和列表格式。"""
    outline = plot_dir / "Plot_Outline.md"
    if not outline.is_file():
        return None
    text = outline.read_text(encoding="utf-8")

    # 表格格式: | 章 | 标题 |
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", s):
            cols = [c.strip() for c in s.strip("|").split("|")]
            if len(cols) >= 2:
                try:
                    # 第0列是卷号，第1列是章号
                    if len(cols) >= 3 and int(cols[1]) == chapter_num:
                        title = cols[2] if len(cols) > 2 else ""
                        if title and title not in ("标题", "---", "未命名"):
                            return title
                except ValueError:
                    pass
    # 列表格式: - 第X章：标题
    for line in text.splitlines():
        m = re.match(rf"-\s*第{chapter_num}章[：:]\s*(.+)", line.strip())
        if m:
            return m.group(1).strip()

    return None


# ====================================================================
#  场景分析
# ====================================================================

def analyze_prev_chapter(chapter_path: Path) -> dict | None:
    script = SCRIPT_DIR / "analyze_scene_type.py"
    if not script.is_file():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--file", str(chapter_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except (subprocess.TimeoutExpired, Exception):
        return None
    json_match = re.search(r"\{[\s\S]*\}", result.stdout)
    if not json_match:
        return None
    try:
        return json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None


# ====================================================================
#  上一章信息
# ====================================================================

def extract_last_narrative(text: str, max_chars: int = 500) -> str:
    cutoff = re.search(r"\n##\s+本章元数据", text)
    if cutoff:
        text = text[:cutoff.start()]
    _, body = parse_frontmatter(text)
    if body is None:
        body = text
    body = re.sub(r"^#\s+.+\n", "", body).strip()
    if len(body) <= max_chars:
        return body
    return "…" + body[-(max_chars - 1):]


def infer_mood(text: str) -> str:
    scores = {
        "紧张": len(re.findall(r"紧张|急促|冷汗|心跳|攥紧|颤抖", text)),
        "悲伤": len(re.findall(r"眼泪|哭|哽咽|舍不得|告别", text)),
        "悬疑": len(re.findall(r"秘密|真相|到底|不对劲|异常", text)),
        "轻松": len(re.findall(r"笑|温暖|阳光|番茄炒蛋|不错", text)),
        "压抑": len(re.findall(r"沉默|沉重|衰退|代价|失去", text)),
        "希望": len(re.findall(r"新的|也许|还能|活下去|未来", text)),
        "平静": len(re.findall(r"安静|平静|看着|躺着|云|窗", text)),
    }
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "中性叙事"


def get_prev_chapter_info(chapters_dir: Path, target_chapter: int | None = None) -> dict | None:
    existing = get_chapter_files(chapters_dir)
    if not existing:
        return None
    if target_chapter is not None:
        # 找到比 target_chapter 小1的章节
        prev = [(n, p) for n, p in existing if n == target_chapter - 1]
        if prev:
            prev_num, prev_path = prev[0]
        else:
            # 取比 target_chapter 小的最大章号
            smaller = [(n, p) for n, p in existing if n < target_chapter]
            if not smaller:
                return None
            prev_num, prev_path = smaller[-1]
    else:
        prev_num, prev_path = existing[-1]
    full_text = prev_path.read_text(encoding="utf-8")
    ending = extract_last_narrative(full_text, 500)
    mood = infer_mood(ending)
    return {
        "chapter_num": prev_num,
        "path": prev_path,
        "ending_text": ending,
        "mood": mood,
        "scene_analysis": analyze_prev_chapter(prev_path),
    }


# ====================================================================
#  内部规划
# ====================================================================

def plan_chapter(chapter_num: int, prev_scene: dict | None) -> dict:
    params = {
        "pov": "林子轩", "conflict_type": "人与人", "rhythm": "中",
        "time_gap": "紧接上一章", "has_cliffhanger": True, "expected_hooks": "1-2",
    }
    if prev_scene:
        if prev_scene.get("has_cliffhanger"):
            params["has_cliffhanger"] = True
    if chapter_num <= 6:
        params["expected_hooks"] = "3-4"
    return params


# ====================================================================
#  上下文
# ====================================================================

def read_context(context_path: Path) -> str:
    return context_path.read_text(encoding="utf-8") if context_path.is_file() else ""


# ====================================================================
#  提示词构造
# ====================================================================

def build_prompt(
    chapter_num: int, title: str, prev_info: dict | None,
    context_text: str, goal: str, params: dict, ai_generate_title: bool,
) -> str:
    ctx = context_text[-20000:] if len(context_text) > 20000 else context_text
    parts = []

    parts.append("你是一个专业的小说家。请续写第%d章。" % chapter_num)
    parts.append("")

    # --- 标题生成（放在开头，强调优先级） ---
    if ai_generate_title:
        parts.append("【第一步：生成标题】")
        parts.append("请在输出任何其他内容之前，第一行输出本章标题。格式为：")
        parts.append("标题：XXX")
        parts.append("XXX 是标题文字，不超过 10 字。例如：标题：深渊回响")
        parts.append("这一行仅用于脚本解析，不会写入最终文件。")
        parts.append("")

    parts.append("## 本章规划要素")
    parts.append("- 节奏：%s" % params["rhythm"])
    parts.append("- 冲突类型：%s" % params["conflict_type"])
    parts.append("- 视角人物：%s" % params["pov"])
    parts.append("- 时间间隔：%s" % params["time_gap"])
    parts.append("- 结尾悬念：%s" % ("是" if params["has_cliffhanger"] else "否"))
    parts.append("- 预计新伏笔：%s 条" % params["expected_hooks"])
    parts.append("")

    if prev_info and prev_info.get("scene_analysis"):
        sa = prev_info["scene_analysis"]
        parts.append("## 上一章场景分析")
        parts.append("- 类型：%s | 节奏：%s" % (sa.get("scene_type", "?"), sa.get("rhythm", "?")))
        parts.append("")

    if prev_info:
        parts.append("## 上一章结尾")
        parts.append(prev_info["ending_text"])
        parts.append("情绪: %s" % prev_info["mood"])
        parts.append("")

    parts.append("## 当前状态")
    parts.append(ctx)
    parts.append("## 本章目标: %s" % goal)
    parts.append("")

    # --- 输出格式 ---
    parts.append("## 输出格式（严格按顺序）")
    if ai_generate_title:
        parts.append("第1行: 标题：XXX")
    parts.append("然后: <!-- scene_self_check ... --> 自检清单（HTML注释）")
    parts.append("然后: YAML frontmatter（```yaml```，不含 chapter_number 和 title）")
    parts.append("然后: 正文，第一行 '# 第%d章 %s'" % (chapter_num, title))
    parts.append("然后: 元数据区块（```metadata```）：新人物/新伏笔/已填坑/世界观")
    parts.append("最后: 规划行（```plottable```），一行 Markdown 表格行：")
    parts.append("| 卷 | 章 | 标题 | 核心事件（15字以内） | POV | 新增人物 | 埋坑（伏笔ID或描述） | 字数预估 |")
    parts.append("例如: | 1 | 16 | 星海独白 | 林子轩在冬眠中与宇进行深层意识对话 | 林子轩 | 无 | 宇的真实记忆碎片开始浮现 | 2400 |")
    parts.append("卷填1，章填%d，标题填实际标题，其余列根据正文内容如实填写。" % chapter_num)
    parts.append("")
    parts.append("另外，在 plottable 之后，输出以下两个代码块：")
    parts.append("")
    parts.append("`hooks_table")
    parts.append("（本意新增的伏笔，每行一条，格式同伏笔填坑规划表格：| 伏笔描述 | 第%d章 | 计划填坑章 | 说明 |）" % chapter_num)
    parts.append("如果没有新增伏笔，写：无")
    parts.append("`")
    parts.append("")
    parts.append("`continuity")
    parts.append("（1-2句话，描述本章结尾状态和下一章的衔接要点，用于更新\"已写章节与后续衔接说明\"）")
    parts.append("格式：- **第%d章《标题》已完成**，衔接要点：..." % chapter_num)
    parts.append("`")

    return "\n".join(parts)
def call_api(prompt: str, api_key: str, model: str) -> str | None:
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.8, "max_tokens": 8192}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=300)
    except requests.exceptions.RequestException as e:
        log.error("[ERROR] API 请求失败: %s", e)
        return None
    if resp.status_code != 200:
        log.error("[ERROR] 状态码 %d", resp.status_code)
        return None
    data = resp.json()
    choices = data.get("choices")
    if not choices:
        return None
    content = choices[0].get("message", {}).get("content", "")
    log.info("  [OK] 返回 %d 字符", len(content))
    return content


# ====================================================================
#  解析 & 写入
# ====================================================================

def parse_and_write(raw: str, chapters_dir: Path, chapter_num: int,
                    title: str, params: dict) -> tuple[Path, str, str, str]:
    # 提取 AI 自拟标题
    ai_title_match = re.search(r"^标题[：:]\s*(.{1,15})", raw, re.MULTILINE)
    if ai_title_match and title == "未命名":
        title = ai_title_match.group(1).strip()
        log.info("  AI 自拟标题: %s", title)

    yaml_text = metadata_text = plottable_line = ""
    hooks_text = continuity_text = ""
    remaining = raw.strip()

    # 提取各代码块（用 chr(96) 避免反引号转义问题）
    B = chr(96)

    # plottable
    pm = re.search(B + "{3,}plottable\\s*\\n(.*?)\\n" + B + "{3,}", remaining, re.DOTALL)
    if pm:
        plottable_line = pm.group(1).strip()
        remaining = remaining[:pm.start()] + remaining[pm.end():]

    # hooks_table
    hm = re.search(B + "{3,}hooks_table\\s*\\n(.*?)\\n" + B + "{3,}", remaining, re.DOTALL)
    if hm:
        hooks_text = hm.group(1).strip()
        remaining = remaining[:hm.start()] + remaining[hm.end():]

    # continuity
    cm = re.search(B + "{3,}continuity\\s*\\n(.*?)\\n" + B + "{3,}", remaining, re.DOTALL)
    if cm:
        continuity_text = cm.group(1).strip()
        remaining = remaining[:cm.start()] + remaining[cm.end():]

    # yaml
    m = re.search(B + "{3,}yaml\\s*\\n(.*?)\\n" + B + "{3,}", remaining, re.DOTALL)
    if m:
        yaml_text = m.group(1).strip()
        remaining = remaining[:m.start()] + remaining[m.end():]

    # metadata
    m = re.search(B + "{3,}metadata\\s*\\n(.*?)\\n" + B + "{3,}", remaining, re.DOTALL)
    if m:
        metadata_text = m.group(1).strip()
        remaining = remaining[:m.start()] + remaining[m.end():]

    # 清理
    remaining = re.sub(r"<!-- scene_self_check.*?-->", "", remaining, flags=re.DOTALL)
    remaining = re.sub(r"^标题[：:].+\n", "", remaining, flags=re.MULTILINE)
    body = re.sub(r"^#\s+第\d+章\s+.*\n*", "", remaining, flags=re.MULTILINE).strip()
    # 如果 metadata_text 为空，尝试从 body 中提取 **metadata**: 格式
    if not metadata_text:
        mm = re.search(r'\*\*metadata\*\*\s*:\s*\n(.*?)(?=\n\*\*plottable|\n\n\n|\n---\s*\n|$)', body, re.DOTALL)
        if mm:
            metadata_text = mm.group(1).strip()
            body = body[:mm.start()] + body[mm.end():]

    # 清理 body 中的残留格式标记
    body = re.sub(r'\*\*plottable\*\*.*?(?=\n\n|$)', '', body, flags=re.DOTALL)
    body = re.sub(r'\n\s*(?:hooks_table|continuity)\s*\n.*?(?=\n\n|\n##|$)', '', body, flags=re.DOTALL)
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = body.strip()

    yaml_lines = [l for l in yaml_text.splitlines()
                  if not re.match(r"^(chapter_number|title)\s*:", l.strip())]
    yaml_clean = "\n".join(yaml_lines).strip()

    if not metadata_text:
        metadata_text = "### 新出场人物\n无\n\n### 新伏笔/坑\n无\n\n### 已填旧坑\n无\n\n### 世界观/地点/设定补充\n无"

    final = f"""---
chapter_number: {chapter_num}
title: "{title}"
rhythm: {params.get("rhythm", "中")}
conflict_type: {params.get("conflict_type", "人与人")}
pov: {params.get("pov", "未知")}
time_gap: {params.get("time_gap", "")}
has_cliffhanger: {str(params.get("has_cliffhanger", True)).lower()}
{yaml_clean if yaml_clean else 'status: draft'}
---

# 第{chapter_num}章 {title}

{body}

## 本章元数据

{metadata_text}
"""

    output_path = chapters_dir / f"第{chapter_num}章 {title}.md"
    output_path.write_text(final, encoding="utf-8")
    log.info("  [OK] 已写入: %s (%d 字符)", output_path, len(final))
    return output_path, plottable_line, hooks_text, continuity_text


# ====================================================================
#  更新规划表
# ====================================================================

def update_plot_outline(novel: str, chapter: int, title: str, plottable: str = "",
                         hooks: str = "", continuity: str = ""):
    script = SCRIPT_DIR / "update_plot_outline.py"
    if not script.is_file():
        log.warning("  [WARN] update_plot_outline.py 不存在，跳过")
        return
    args = [sys.executable, str(script), "--novel", novel,
             "--chapter", str(chapter), "--title", title]
    if plottable:
        args.extend(["--line", plottable])
    if hooks and hooks != "无":
        args.extend(["--hooks", hooks])
    if continuity:
        args.extend(["--continuity", continuity])
    try:
        subprocess.run(args, timeout=15)
    except Exception as e:
        log.warning("  [WARN] 更新规划表失败: %s", e)


# ====================================================================
#  主流程
# ====================================================================

def generate_chapter(novel_dir: Path, api_key: str, model: str, goal: str,
                     target_chapter: int | None = None):
    novel_name = novel_dir.name
    chapters_dir = novel_dir / "04_Chapters"
    plot_dir = novel_dir / "02_Plot"
    context_path = novel_dir / "05_Context" / "Current_Context.md"

    log.info("=" * 55)
    log.info("  生成章节: %s", novel_name)

    # 1. 章号
    chapters_dir.mkdir(parents=True, exist_ok=True)
    if target_chapter:
        next_ch = target_chapter
    else:
        existing = get_chapter_files(chapters_dir)
        next_ch = existing[-1][0] + 1 if existing else 1
    log.info("  章节: 第%d章", next_ch)

    # 2. 标题
    title = get_title_from_plot(plot_dir, next_ch)
    ai_generate_title = (title is None)
    if title:
        log.info("  规划标题: %s", title)
    else:
        title = "未命名"
        log.info("  无规划标题，AI 将自拟")

    # 3. 上一章信息
    prev_info = get_prev_chapter_info(chapters_dir, next_ch)
    if prev_info:
        log.info("  上一章: 第%d章 | 情绪: %s", prev_info["chapter_num"], prev_info["mood"])

    # 4. 规划
    prev_scene = prev_info.get("scene_analysis") if prev_info else None
    params = plan_chapter(next_ch, prev_scene)

    # 5. 上下文
    context_text = read_context(context_path)

    # 6. 提示词 & API
    prompt = build_prompt(next_ch, title, prev_info, context_text, goal, params, ai_generate_title)
    log.info("  提示词: %d 字符", len(prompt))
    result = call_api(prompt, api_key, model)
    if result is None:
        log.error("[ERROR] 生成失败")
        return

    # 7. 写入
    ch_path, plottable, hooks_text, continuity_text = parse_and_write(result, chapters_dir, next_ch, title, params)
    final_title = ch_path.stem.replace(f"第{next_ch}章 ", "")

    # 8. 更新规划表
    update_plot_outline(novel_name, next_ch, final_title, plottable, hooks_text, continuity_text)

    # 9. 输出给父脚本
    print(f"CHAPTER={next_ch}|{final_title}")

    log.info("[OK] 完成: %s", ch_path.name)
    log.info("=" * 55)


def main():
    parser = argparse.ArgumentParser(description="增强版章节生成器")
    parser.add_argument("--novel", type=str, required=True, help="小说名")
    parser.add_argument("--goal", type=str, default="自然推进剧情", help="写作目标")
    parser.add_argument("--chapter", type=int, default=None, help="指定章节号")
    parser.add_argument("--api-key", type=str, default=None, help="API Key")
    parser.add_argument("--model", type=str, default="deepseek-chat", help="模型名")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        log.error("[ERROR] 未提供 API Key")
        sys.exit(1)

    target = SCRIPT_DIR / "Novels" / args.novel
    if not target.is_dir():
        log.error("[ERROR] 目录不存在: %s", target)
        sys.exit(1)

    generate_chapter(target, api_key, args.model, args.goal, args.chapter)
    log.info("[OK] 全部完成。")


if __name__ == "__main__":
    main()
