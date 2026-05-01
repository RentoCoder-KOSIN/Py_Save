"""
py_save/save_manager.py  –  SQLite ベースのセーブデータ管理コア
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Any, Optional


# ------------------------------------------------------------------ #
#  例外                                                                #
# ------------------------------------------------------------------ #

class SaveError(Exception):
    """py_save 共通基底例外"""

class SlotNotFoundError(SaveError):
    """指定スロットが存在しない"""

class SlotAlreadyExistsError(SaveError):
    """スロットがすでに存在する（overwrite=False 時）"""


# ------------------------------------------------------------------ #
#  SaveManager                                                         #
# ------------------------------------------------------------------ #

class SaveManager:
    """
    SQLite をバックエンドとしたゲーム向けセーブデータ管理クラス。

    Parameters
    ----------
    directory : str
        セーブファイルを置くフォルダ（存在しなければ自動作成）。
    db_name : str
        SQLite ファイル名（デフォルト: "savedata.db"）。
    backup : bool
        True にすると save / delete の前に自動バックアップを保存。
    """

    def __init__(
        self,
        directory: str = "saves",
        db_name: str = "savedata.db",
        backup: bool = True,
    ):
        self._dir = directory
        self._backup = backup
        os.makedirs(directory, exist_ok=True)

        db_path = os.path.join(directory, db_name)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    # ---- 内部 --------------------------------------------------------

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS saves (
                slot        TEXT PRIMARY KEY,
                data        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                saved_at    TEXT NOT NULL,
                play_time   REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS saves_backup (
                slot         TEXT,
                data         TEXT,
                created_at   TEXT,
                saved_at     TEXT,
                play_time    REAL,
                backed_up_at TEXT
            );
        """)
        self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _key(slot) -> str:
        return str(slot)

    def _fetch(self, slot) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM saves WHERE slot=?", (self._key(slot),)
        ).fetchone()
        if row is None:
            raise SlotNotFoundError(f"スロット {slot!r} は存在しません")
        return row

    def _backup_slot(self, slot) -> None:
        try:
            row = self._fetch(slot)
        except SlotNotFoundError:
            return
        self._conn.execute(
            "DELETE FROM saves_backup WHERE slot=?", (self._key(slot),)
        )
        self._conn.execute(
            "INSERT INTO saves_backup VALUES (?,?,?,?,?,?)",
            (row["slot"], row["data"], row["created_at"],
             row["saved_at"], row["play_time"], self._now())
        )
        self._conn.commit()

    @staticmethod
    def _strip_meta(data: dict) -> dict:
        return {k: v for k, v in data.items() if not k.startswith("_")}

    # ---- 公開 API ----------------------------------------------------

    def create(
        self,
        slot,
        data: dict,
        play_time: float = 0.0,
        overwrite: bool = False,
    ) -> None:
        """新しいセーブスロットを作成する。"""
        key = self._key(slot)
        exists = self._conn.execute(
            "SELECT 1 FROM saves WHERE slot=?", (key,)
        ).fetchone()

        if exists and not overwrite:
            raise SlotAlreadyExistsError(
                f"スロット {slot!r} はすでに存在します (overwrite=True で上書き可)"
            )
        if exists and self._backup:
            self._backup_slot(slot)

        now = self._now()
        self._conn.execute("""
            INSERT INTO saves (slot, data, created_at, saved_at, play_time)
            VALUES (?,?,?,?,?)
            ON CONFLICT(slot) DO UPDATE SET
                data=excluded.data, saved_at=excluded.saved_at,
                play_time=excluded.play_time
        """, (key, json.dumps(self._strip_meta(data), ensure_ascii=False),
              now, now, play_time))
        self._conn.commit()

    def load(self, slot) -> dict:
        """セーブデータを読み込む（メタキー _* 付き）。"""
        row = self._fetch(slot)
        data = json.loads(row["data"])
        data.update({
            "_slot":       row["slot"],
            "_created_at": row["created_at"],
            "_saved_at":   row["saved_at"],
            "_play_time":  row["play_time"],
        })
        return data

    def save(
        self,
        slot,
        data: dict,
        play_time: Optional[float] = None,
    ) -> None:
        """既存スロットにデータを上書き保存する。"""
        row = self._fetch(slot)
        if self._backup:
            self._backup_slot(slot)
        pt = play_time if play_time is not None else row["play_time"]
        self._conn.execute(
            "UPDATE saves SET data=?, saved_at=?, play_time=? WHERE slot=?",
            (json.dumps(self._strip_meta(data), ensure_ascii=False),
             self._now(), pt, self._key(slot))
        )
        self._conn.commit()

    def update(
        self,
        slot,
        fields: dict,
        play_time: Optional[float] = None,
    ) -> None:
        """指定フィールドだけを部分更新する。"""
        row = self._fetch(slot)
        if self._backup:
            self._backup_slot(slot)
        current = json.loads(row["data"])
        current.update(self._strip_meta(fields))
        pt = play_time if play_time is not None else row["play_time"]
        self._conn.execute(
            "UPDATE saves SET data=?, saved_at=?, play_time=? WHERE slot=?",
            (json.dumps(current, ensure_ascii=False),
             self._now(), pt, self._key(slot))
        )
        self._conn.commit()

    def delete(self, slot) -> None:
        """スロットを消去する（backup=True なら事前バックアップ）。"""
        self._fetch(slot)
        if self._backup:
            self._backup_slot(slot)
        self._conn.execute(
            "DELETE FROM saves WHERE slot=?", (self._key(slot),)
        )
        self._conn.commit()

    def restore_backup(self, slot) -> None:
        """直前のバックアップからスロットを復元する。"""
        row = self._conn.execute(
            "SELECT * FROM saves_backup WHERE slot=?", (self._key(slot),)
        ).fetchone()
        if row is None:
            raise SlotNotFoundError(f"スロット {slot!r} のバックアップがありません")
        self._conn.execute("""
            INSERT INTO saves (slot, data, created_at, saved_at, play_time)
            VALUES (?,?,?,?,?)
            ON CONFLICT(slot) DO UPDATE SET
                data=excluded.data, saved_at=excluded.saved_at,
                play_time=excluded.play_time
        """, (row["slot"], row["data"], row["created_at"],
              row["saved_at"], row["play_time"]))
        self._conn.commit()

    def exists(self, slot) -> bool:
        """スロットが存在すれば True。"""
        return self._conn.execute(
            "SELECT 1 FROM saves WHERE slot=?", (self._key(slot),)
        ).fetchone() is not None

    def list(self) -> list:
        """全スロットのメタ情報一覧を返す。"""
        rows = self._conn.execute(
            "SELECT slot, created_at, saved_at, play_time FROM saves ORDER BY slot"
        ).fetchall()
        return [dict(r) for r in rows]

    def copy(self, src, dst, overwrite: bool = False) -> None:
        """スロットをコピーする。"""
        row = self._fetch(src)
        self.create(dst, json.loads(row["data"]),
                    play_time=row["play_time"], overwrite=overwrite)

    def slot_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM saves").fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __repr__(self):
        return (f"SaveManager(dir={self._dir!r}, "
                f"slots={self.slot_count()}, backup={self._backup})")
