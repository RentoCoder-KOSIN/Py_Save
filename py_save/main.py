"""
py_save/main.py  –  CLI エントリポイント

ターミナルで `py_save` と打つと実行される。
セーブデータの簡易確認ツールとして使用できる。
"""

import sys
import os
from .save_manager import SaveManager, SlotNotFoundError


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="py_save",
        description="py_save セーブデータ管理ツール",
    )
    parser.add_argument(
        "--dir", default="saves", help="セーブデータのフォルダ（デフォルト: saves）"
    )
    subparsers = parser.add_subparsers(dest="command")

    # list
    subparsers.add_parser("list", help="セーブスロット一覧を表示")

    # show
    p_show = subparsers.add_parser("show", help="スロットの中身を表示")
    p_show.add_argument("slot", help="スロット番号/名前")

    # delete
    p_del = subparsers.add_parser("delete", help="スロットを消去")
    p_del.add_argument("slot", help="スロット番号/名前")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    mgr = SaveManager(args.dir)

    if args.command == "list":
        slots = mgr.list()
        if not slots:
            print("セーブデータが見つかりません")
            return
        print(f"{'スロット':>10}  {'作成日時':>19}  {'最終保存':>19}  {'プレイ時間':>10}")
        print("-" * 70)
        for s in slots:
            h = int(s['play_time'] // 3600)
            m = int((s['play_time'] % 3600) // 60)
            print(f"{s['slot']:>10}  {s['created_at']:>19}  {s['saved_at']:>19}  {h:02d}:{m:02d}")

    elif args.command == "show":
        try:
            import json
            data = mgr.load(args.slot)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except SlotNotFoundError as e:
            print(f"エラー: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "delete":
        try:
            mgr.delete(args.slot)
            print(f"スロット {args.slot!r} を削除しました")
        except SlotNotFoundError as e:
            print(f"エラー: {e}", file=sys.stderr)
            sys.exit(1)

    mgr.close()


if __name__ == "__main__":
    main()
