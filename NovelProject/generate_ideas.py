#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_ideas.py -- 调用 DeepSeek API，根据当前故事状态和章节规划生成下一章灵感。

用法:
    python generate_ideas.py --novel "文明升阶"
    python generate_ideas.py --novel "文明升阶" --api-key sk-xxx --append
    python generate_ideas.py --novel "文明升阶" --model deepseek-chat

环境变量: DEEPSEEK_API_KEY 可替代 --api-key
依赖: requests (pip install requests)
"""

import argparse
import io
import logging
import os
from pathlib import Path

# 自动加载项目根目录的 .env 文件
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.is_file():
    with open(_ENV_FILE, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip().strip("'").strip('"')
                if _key and _key not in os.environ:
                    os.environ[_key] = _val
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# 依赖检查
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError:
    print("错误: 缺少 requests 库。请安装：", file=sys.stderr)
    print("  pip install requests", file=sys.stderr)
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
log = logging.getLogger("generate_ideas")


# ===================================================================
#  工具函数
# ===================================================================

def read_context_file(context_path: Path) -> str | None:
    """读取 Current_Context.md 完整内容。"""
    if not context_path.is_file():
        log.warning("[WARN] 未找到 %s", context_path)
        return None
    return context_path.read_text(encoding="utf-8")


def read_plot_files(plot_dir: Path) -> str:
    """读取章节规划表内容。

    优先读取 Plot_Outline.md，否则读取该目录下所有 .md 文件拼接。
    """
    if not plot_dir.is_dir():
        log.warning("[WARN] 未找到 %s 目录", plot_dir)
        return "（无章节规划数据）"

    outline_file = plot_dir / "Plot_Outline.md"
    if outline_file.is_file():
        log.info("  读取章节规划: %s", outline_file.name)
        return outline_file.read_text(encoding="utf-8")

    # 回退：读取所有 md 文件
    md_files = sorted(plot_dir.glob("*.md"))
    if not md_files:
        return "（无章节规划数据）"

    log.info("  读取章节规划: %d 个文件", len(md_files))
    parts = []
    for f in md_files:
        parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def build_prompt(context_text: str, plot_text: str) -> str:
    """构造发送给 AI 的提示词。"""
    # 截取 context 和 plot 以免超出 token 限制（DeepSeek 上下文 64K，这里保险起见各取后 15000 字符）
    ctx_snippet = context_text[-15000:] if len(context_text) > 15000 else context_text
    plot_snippet = plot_text[-15000:] if len(plot_text) > 15000 else plot_text

    prompt = f"""你是一个专业的小说策划专家。以下是当前故事状态和章节规划表。

---

## 当前故事状态

{ctx_snippet}

---

## 章节规划表

{plot_snippet}

---

请根据以上信息，为下一章生成 3 个不同的剧情灵感。每个灵感格式如下：

### 灵感1：[标题]
- **核心冲突**：（一句话描述本章的核心矛盾或冲突）
- **视角人物**：（建议从哪个角色的视角来写）
- **可填伏笔**：（本章可以回收哪些已有伏笔）
- **新悬念**：（本章可以埋下什么新的悬念）

### 灵感2：[标题]
- **核心冲突**：...
- **视角人物**：...
- **可填伏笔**：...
- **新悬念**：...

### 灵感3：[标题]
- **核心冲突**：...
- **视角人物**：...
- **可填伏笔**：...
- **新悬念**：...

请直接输出灵感，不要添加额外解释或开场白。"""
    return prompt


def call_deepseek_api(prompt: str, api_key: str, model: str) -> str | None:
    """调用 DeepSeek Chat API，返回 AI 生成的文本。"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 4096,
    }

    log.info("  调用 API: %s (temperature=0.8, max_tokens=4096)", model)

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
    except requests.exceptions.Timeout:
        log.error("[ERROR] API 请求超时（超过 120 秒）")
        return None
    except requests.exceptions.ConnectionError:
        log.error("[ERROR] 无法连接到 API 服务器，请检查网络")
        return None
    except requests.exceptions.RequestException as e:
        log.error("[ERROR] API 请求失败: %s", e)
        return None

    if resp.status_code != 200:
        log.error("[ERROR] API 返回错误状态码 %d: %s", resp.status_code, resp.text[:500])
        return None

    try:
        data = resp.json()
    except ValueError:
        log.error("[ERROR] API 返回非 JSON 格式: %s", resp.text[:300])
        return None

    choices = data.get("choices")
    if not choices or len(choices) == 0:
        log.error("[ERROR] API 返回的 choices 为空: %s", str(data)[:500])
        return None

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        log.error("[ERROR] API 返回的内容为空")
        return None

    log.info("  [OK] API 返回 %d 字符", len(content))
    return content


def write_ideas(ideas_dir: Path, content: str, append_mode: bool):
    """将灵感内容写入 Ideas.md。"""
    ideas_dir.mkdir(parents=True, exist_ok=True)
    output_file = ideas_dir / "Ideas.md"

    if append_mode and output_file.is_file():
        existing = output_file.read_text(encoding="utf-8")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = f"\n\n---\n\n## 灵感生成记录 [{timestamp}]\n\n{content}\n"
        output_file.write_text(existing + new_entry, encoding="utf-8")
        log.info("  [OK] 已追加到: %s", output_file)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        full = f"# 下一章灵感\n\n> 生成时间：{timestamp}\n\n{content}\n"
        output_file.write_text(full, encoding="utf-8")
        log.info("  [OK] 已写入: %s", output_file)


# ===================================================================
#  主逻辑
# ===================================================================

def generate_ideas(novel_dir: Path, api_key: str, model: str, append_mode: bool):
    """为一部小说生成灵感。"""
    novel_name = novel_dir.name

    context_file = novel_dir / "05_Context" / "Current_Context.md"
    plot_dir = novel_dir / "02_Plot"
    ideas_dir = novel_dir / "05_Context"

    log.info("=== 处理小说: %s ===", novel_name)

    # 1. 读取当前上下文
    context_text = read_context_file(context_file)
    if context_text is None:
        log.error("[ERROR] 缺少 Current_Context.md，请先运行 build_context.py")
        return

    # 2. 读取章节规划
    plot_text = read_plot_files(plot_dir)

    # 3. 构造提示词
    prompt = build_prompt(context_text, plot_text)
    log.info("  提示词长度: %d 字符", len(prompt))

    # 4. 调用 API
    result = call_deepseek_api(prompt, api_key, model)
    if result is None:
        log.error("[ERROR] 灵感生成失败")
        return

    # 5. 写入文件
    write_ideas(ideas_dir, result, append_mode)


def main():
    parser = argparse.ArgumentParser(
        description="调用 DeepSeek API 根据当前故事状态生成下一章灵感",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python generate_ideas.py --novel "文明升阶" --api-key sk-xxx
    python generate_ideas.py --novel "文明升阶" --api-key sk-xxx --append
    python generate_ideas.py --novel "文明升阶" --model deepseek-chat

环境变量:
    DEEPSEEK_API_KEY       API Key（与 --api-key 二选一）
        """,
    )
    parser.add_argument("--novel", type=str, required=True,
                        help="小说文件夹名（必填，如 '文明升阶'）")
    parser.add_argument("--api-key", type=str, default=None,
                        help="DeepSeek API Key（也可通过环境变量 DEEPSEEK_API_KEY 提供）")
    parser.add_argument("--append", action="store_true",
                        help="追加模式：灵感追加到 Ideas.md 末尾，而非覆盖")
    parser.add_argument("--model", type=str, default="deepseek-chat",
                        help="模型名称（默认: deepseek-chat）")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 获取 API Key（命令行 > 环境变量）
    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        log.error("[ERROR] 未提供 API Key。请通过 --api-key 或环境变量 DEEPSEEK_API_KEY 指定")
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    novels_root = script_dir / "Novels"

    if not novels_root.is_dir():
        log.error("[ERROR] 未找到 Novels 目录: %s", novels_root)
        sys.exit(1)

    target = novels_root / args.novel
    if not target.is_dir():
        log.error("[ERROR] 小说目录不存在: %s", target)
        sys.exit(1)

    generate_ideas(target, api_key, args.model, args.append)

    log.info("[OK] 全部完成。")


if __name__ == "__main__":
    main()

