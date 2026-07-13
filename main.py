"""仮想経営会議 CLI。

使い方:
    python main.py --input examples/case1_設備投資/相談.md --outdir examples/case1_設備投資
    python main.py --consult "配送トラックを1台増やすべきか迷っている。..." --title "トラック増車"

.env の場所を変えたい場合は環境変数 KAIGI_ENV_FILE にパスを指定する。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# llm_client を import する前に .env を読む（既に設定済みの環境変数は上書きしない）
load_dotenv(os.getenv("KAIGI_ENV_FILE") or ".env")

from meeting import run_meeting  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="仮想経営会議: 4人の専門AI + 議長AIが経営相談に提言書を返す")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="相談内容を書いた Markdown/テキストファイル")
    src.add_argument("--consult", type=str, help="相談内容を直接指定")
    parser.add_argument("--title", type=str, default=None, help="提言書のタイトル")
    parser.add_argument("--outdir", type=Path, default=None,
                        help="会議ログと提言書の保存先ディレクトリ（省略時は標準出力のみ）")
    args = parser.parse_args()

    if args.input:
        consultation = args.input.read_text(encoding="utf-8").strip()
        title = args.title or args.input.stem.replace("相談", "").strip("_ ") or "経営相談"
    else:
        consultation = args.consult.strip()
        title = args.title or "経営相談"

    if not consultation:
        print("相談内容が空です", file=sys.stderr)
        return 1

    print(f"=== 仮想経営会議を開始: {title} ===")
    log = run_meeting(consultation, title=title)

    print("\n" + "=" * 60)
    print(log.report)

    if args.outdir:
        args.outdir.mkdir(parents=True, exist_ok=True)
        (args.outdir / "会議ログ.md").write_text(log.to_markdown(), encoding="utf-8")
        (args.outdir / "提言書.md").write_text(log.report + "\n", encoding="utf-8")
        print(f"\n保存しました: {args.outdir}/会議ログ.md, {args.outdir}/提言書.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
