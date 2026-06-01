#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_write.py -- 一键写作编排器（纯编排，零业务逻辑）。

依次调用:
  1. build_context.py     --novel {novel}
  2. generate_ideas.py    --novel {novel}  （仅当 --with-ideas）
  3. generate_chapter.py  --novel {novel} [--goal {goal}]
  4. build_characters.py  --novel {novel}  （仅当 --update-characters）
  5. update_hooks.py      --novel {novel}  （仅当 --update-hooks）

用法:
  python auto_write.py --novel "文明升阶"
  python auto_write.py --novel "文明升阶" --with-ideas --goal "解锁核聚变"
  python auto_write.py --novel "文明升阶" --update-characters --update-hooks
  python auto_write.py --novel "文明升阶" --skip-chapter --update-hooks
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ====================================================================
#  环境变量（.env）
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

SCRIPT_DIR = Path(__file__).resolve().parent


# ====================================================================
#  子脚本调度
# ====================================================================

def _run(name: str, args: list[str], timeout: int = 600) -> bool:
    """调用一个子脚本。实时透传 stdout/stderr。返回 True=成功。"""
    script = SCRIPT_DIR / name
    if not script.is_file():
        print(f"\n[ERROR] 子脚本不存在: {script}", file=sys.stderr)
        print("请确认该文件位于项目根目录下。", file=sys.stderr)
        return False

    cmd = [sys.executable, str(script)] + args

    print()
    print("=" * 60)
    print(f"  >>> {name} {' '.join(args)}")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"\n[ERROR] {name} 超时（{timeout} 秒）", file=sys.stderr)
        return False
    except Exception as e:
        print(f"\n[ERROR] 无法执行 {name}: {e}", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(f"\n[ERROR] {name} 退出码 {result.returncode}", file=sys.stderr)
        return False

    print(f"\n[OK] {name} 完成")
    return True


# ====================================================================
#  主流程
# ====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="一键写作编排器 —— 依次调用子脚本完成完整写作流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python auto_write.py --novel "文明升阶"
  python auto_write.py --novel "文明升阶" --with-ideas --goal "解锁核聚变"
  python auto_write.py --novel "文明升阶" --update-characters --update-hooks
  python auto_write.py --novel "文明升阶" --skip-chapter --update-hooks
        """,
    )
    parser.add_argument("--novel", type=str, required=True,
                        help="小说文件夹名（必填）")
    parser.add_argument("--with-ideas", action="store_true",
                        help="生成章节前调用 generate_ideas.py 生成灵感")
    parser.add_argument("--goal", type=str, default=None,
                        help="本章写作目标，传递给 generate_chapter.py")
    parser.add_argument("--update-characters", action="store_true",
                        help="生成章节后调用 build_characters.py")
    parser.add_argument("--update-hooks", action="store_true",
                        help="调用 update_hooks.py 更新伏笔追踪表")
    parser.add_argument("--skip-chapter", action="store_true",
                        help="跳过章节生成（仅运行其他步骤）")
    args = parser.parse_args()

    novel = args.novel

    print("=" * 60)
    print(f"  一键写作: {novel}")
    print("=" * 60)

    # ---- 步骤 1: build_context.py（必须） ----
    if not _run("build_context.py", ["--novel", novel]):
        sys.exit(1)

    # ---- 步骤 2: generate_ideas.py（可选） ----
    if args.with_ideas:
        if not _run("generate_ideas.py", ["--novel", novel], timeout=120):
            sys.exit(1)

    # ---- 步骤 3: generate_chapter.py（除非 --skip-chapter） ----
    if args.skip_chapter:
        print("\n>>> (跳过) generate_chapter.py")
    else:
        chap_args = ["--novel", novel]
        if args.goal:
            chap_args.extend(["--goal", args.goal])
        if not _run("generate_chapter.py", chap_args):
            sys.exit(1)

    # ---- 步骤 4: build_characters.py（可选） ----
    if args.update_characters:
        if not _run("build_characters.py", ["--novel", novel]):
            sys.exit(1)

    # ---- 步骤 5: update_hooks.py（可选） ----
    if args.update_hooks:
        if not _run("update_hooks.py", ["--novel", novel]):
            sys.exit(1)

    print()
    print("[OK] 一键写作完成！")


if __name__ == "__main__":
    main()
