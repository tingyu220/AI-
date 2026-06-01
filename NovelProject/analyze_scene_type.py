#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_scene_type.py -- 分析章节的场景类型、节奏、冲突等要素。

调用 DeepSeek API，对章节正文进行结构化分析，返回 JSON 结果。

用法:
    python analyze_scene_type.py --file "Novels/文明升阶/04_Chapters/第12章 旧方案点火.md"
    python analyze_scene_type.py --file "..." --api-key sk-xxx

环境变量 / .env: DEEPSEEK_API_KEY
依赖: requests (pip install requests)
"""

import argparse
import io
import json
import logging
import os
import re
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
log = logging.getLogger("analyze_scene")


# ====================================================================
#  正文提取
# ====================================================================

def extract_body(text: str, max_chars: int = 1500) -> str:
    """提取章节正文（跳过 frontmatter 和标题，截取前 max_chars 字）。"""
    # 去掉 YAML frontmatter
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if m:
        text = text[m.end():]

    # 去掉 # 标题行
    text = re.sub(r"^#\s+第\d+章\s+.+\n", "", text)

    # 去掉 ## 本章元数据 之后的内容
    cutoff = re.search(r"\n##\s+本章元数据", text)
    if cutoff:
        text = text[:cutoff.start()]

    body = text.strip()
    if len(body) > max_chars:
        return body[:max_chars]
    return body


# ====================================================================
#  API 分析
# ====================================================================

def build_prompt(chapter_text: str) -> str:
    return f"""请分析以下小说章节内容，返回一个 JSON 对象（不要其他任何文字），包含以下字段：

- scene_type: 场景类型（从以下选择一个：对话/谈判、战斗/对抗、探索/解谜、情感/内心戏、日常/过渡、悬疑/惊悚、高潮/转折、铺垫/伏笔、回忆/插叙、群像/多视角）
- rhythm: 节奏（快/中/慢）
- conflict_type: 主要冲突类型（人与自我/人与人/人与社会/人与自然）
- pov: 主要视角人物（人名，无法确定则填"未知"）
- has_cliffhanger: 结尾是否有悬念（true/false）
- dominant_sense: 最突出的感官描写（视觉/听觉/触觉/嗅觉/味觉/无）

章节内容：
{chapter_text}"""


def call_api(prompt: str, api_key: str, model: str) -> dict | None:
    """调用 DeepSeek API 返回解析后的 JSON 字典。"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,   # 低温度保证结构化输出
        "max_tokens": 512,
    }

    log.info("  调用 API: %s", model)

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.exceptions.Timeout:
        log.error("[ERROR] 超时")
        return None
    except requests.exceptions.RequestException as e:
        log.error("[ERROR] 请求失败: %s", e)
        return None

    if resp.status_code != 200:
        log.error("[ERROR] 状态码 %d: %s", resp.status_code, resp.text[:300])
        return None

    try:
        data = resp.json()
    except ValueError:
        log.error("[ERROR] 非 JSON: %s", resp.text[:200])
        return None

    choices = data.get("choices")
    if not choices:
        log.error("[ERROR] choices 为空")
        return None

    content = choices[0].get("message", {}).get("content", "").strip()
    if not content:
        log.error("[ERROR] 返回空内容")
        return None

    # 解析 JSON（可能被 ```json ... ``` 包裹）
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_match:
        content = json_match.group(1).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        log.warning("[WARN] JSON 解析失败，尝试修复: %s", e)
        # 尝试提取裸 JSON 对象
        brace_match = re.search(r"\{[\s\S]*\}", content)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        log.error("[ERROR] 无法解析返回内容: %s", content[:200])
        return None


# ====================================================================
#  主逻辑
# ====================================================================

def analyze(file_path: Path, api_key: str, model: str):
    if not file_path.is_file():
        log.error("[ERROR] 文件不存在: %s", file_path)
        sys.exit(1)

    log.info("  分析: %s", file_path.name)

    # 读取并提取正文
    full_text = file_path.read_text(encoding="utf-8")
    body = extract_body(full_text)
    log.info("  正文截取: %d 字符", len(body))

    # 构造提示词并调用
    prompt = build_prompt(body)
    result = call_api(prompt, api_key, model)

    if result is None:
        log.error("[ERROR] 分析失败")
        sys.exit(1)

    # 输出结果
    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()
    log.info("[OK] 分析完成")


def main():
    parser = argparse.ArgumentParser(
        description="分析章节的场景类型、节奏、冲突等要素",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python analyze_scene_type.py --file "Novels/文明升阶/04_Chapters/第12章 旧方案点火.md"
        """,
    )
    parser.add_argument("--file", type=str, required=True,
                        help="章节文件的完整路径")
    parser.add_argument("--api-key", type=str, default=None,
                        help="DeepSeek API Key")
    parser.add_argument("--model", type=str, default="deepseek-chat",
                        help="模型名（默认: deepseek-chat）")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        log.error("[ERROR] 未提供 API Key。请在 .env 中设置或通过 --api-key 指定")
        sys.exit(1)

    analyze(Path(args.file), api_key, args.model)


if __name__ == "__main__":
    main()
