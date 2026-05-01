"""
py_save/pygame_save.py  –  pygame ゲームループとの連携ユーティリティ

pygame がインストールされていない環境でも import エラーにならないよう
遅延インポートで対応しています。
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Optional
import time

from .save_manager import SaveManager

if TYPE_CHECKING:
    pass


class PygameSaveManager(SaveManager):
    """
    pygame ゲームループと統合したセーブ管理クラス。
    SaveManager のすべての機能 + pygame 向け拡張を提供します。

    追加機能
    --------
    - プレイ時間の自動計測
    - オートセーブ（一定間隔で自動保存）
    - pygame.key のキー入力でクイックセーブ / ロード

    Parameters
    ----------
    directory    : セーブフォルダ
    db_name      : SQLite ファイル名
    backup       : 自動バックアップ有無
    autosave_sec : オートセーブ間隔（秒）。0 で無効。
    autosave_slot: オートセーブ先スロット名
    """

    def __init__(
        self,
        directory: str = "saves",
        db_name: str = "savedata.db",
        backup: bool = True,
        autosave_sec: float = 300.0,
        autosave_slot: str = "autosave",
    ):
        super().__init__(directory, db_name, backup)
        self._autosave_sec  = autosave_sec
        self._autosave_slot = autosave_slot
        self._session_start = time.time()
        self._last_autosave = time.time()
        self._data_getter: Optional[Callable[[], dict]] = None

    # ---------------------------------------------------------------- #
    #  プレイ時間                                                        #
    # ---------------------------------------------------------------- #

    def session_time(self) -> float:
        """現在セッションの経過秒数を返す。"""
        return time.time() - self._session_start

    def total_play_time(self, slot) -> float:
        """セーブ済みプレイ時間 + 今セッションの合計秒数を返す。"""
        data = self.load(slot)
        return data["_play_time"] + self.session_time()

    def format_play_time(self, seconds: float) -> str:
        """秒数を "HH:MM:SS" 形式に変換する。"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    # ---------------------------------------------------------------- #
    #  セーブ（プレイ時間を自動付与）                                    #
    # ---------------------------------------------------------------- #

    def save_with_time(self, slot, data: dict) -> None:
        """
        プレイ時間を自動計算して save する便利メソッド。
        既存のプレイ時間 + 今セッションを合算して記録します。
        """
        if self.exists(slot):
            existing = self.load(slot)
            total = existing["_play_time"] + self.session_time()
        else:
            total = self.session_time()
        self.save(slot, data, play_time=total)

    def create_with_time(self, slot, data: dict, overwrite: bool = False) -> None:
        """プレイ時間 0 で新規作成（セッション開始タイミングでリセット）。"""
        self._session_start = time.time()
        self.create(slot, data, play_time=0.0, overwrite=overwrite)

    # ---------------------------------------------------------------- #
    #  オートセーブ                                                      #
    # ---------------------------------------------------------------- #

    def set_data_getter(self, getter: Callable[[], dict]) -> None:
        """
        オートセーブ時に呼ばれるデータ取得関数を登録する。

        Parameters
        ----------
        getter : 引数なし・dict 返却の callable
                 例: lambda: game.get_save_data()

        Example
        -------
        mgr.set_data_getter(lambda: {
            "player": player.name,
            "hp":     player.hp,
            "pos":    [player.x, player.y],
        })
        """
        self._data_getter = getter

    def tick(self) -> bool:
        """
        ゲームループの毎フレームから呼ぶ。
        オートセーブ間隔に達していれば自動保存し True を返す。

        Returns
        -------
        bool : オートセーブが実行されたら True

        Example
        -------
        # ゲームループ内
        while running:
            ...
            if mgr.tick():
                print("オートセーブ完了")
        """
        if self._autosave_sec <= 0 or self._data_getter is None:
            return False
        if time.time() - self._last_autosave >= self._autosave_sec:
            data = self._data_getter()
            if self.exists(self._autosave_slot):
                self.save_with_time(self._autosave_slot, data)
            else:
                self.create_with_time(self._autosave_slot, data, overwrite=True)
            self._last_autosave = time.time()
            return True
        return False

    # ---------------------------------------------------------------- #
    #  pygame キー入力連携                                               #
    # ---------------------------------------------------------------- #

    def handle_keydown(
        self,
        event,
        data_getter: Optional[Callable[[], dict]] = None,
        quicksave_key: int = None,
        quickload_key: int = None,
        quicksave_slot=9,
    ) -> Optional[str]:
        """
        pygame の KEYDOWN イベントを渡すと、クイックセーブ / ロードを処理する。

        Parameters
        ----------
        event          : pygame.event.Event（KEYDOWN）
        data_getter    : クイックセーブ時のデータ取得関数（None なら set_data_getter 優先）
        quicksave_key  : クイックセーブキー（pygame.K_F5 など）
        quickload_key  : クイックロードキー（pygame.K_F9 など）
        quicksave_slot : クイックセーブ先スロット（デフォルト: 9）

        Returns
        -------
        "saved" / "loaded" / None

        Example
        -------
        import pygame
        from py_save import PygameSaveManager

        mgr = PygameSaveManager("saves/")
        mgr.set_data_getter(lambda: game.get_data())

        for event in pygame.event.get():
            result = mgr.handle_keydown(
                event,
                quicksave_key=pygame.K_F5,
                quickload_key=pygame.K_F9,
            )
            if result == "saved":
                show_message("クイックセーブ完了")
            elif result == "loaded":
                game.load_data(mgr.load(quicksave_slot))
        """
        try:
            import pygame
        except ImportError:
            raise ImportError("pygame が必要です: pip install pygame")

        if event.type != pygame.KEYDOWN:
            return None

        getter = data_getter or self._data_getter

        if quicksave_key and event.key == quicksave_key:
            if getter is None:
                raise ValueError("data_getter が設定されていません")
            data = getter()
            if self.exists(quicksave_slot):
                self.save_with_time(quicksave_slot, data)
            else:
                self.create_with_time(quicksave_slot, data, overwrite=True)
            return "saved"

        if quickload_key and event.key == quickload_key:
            if self.exists(quicksave_slot):
                return "loaded"

        return None

    # ---------------------------------------------------------------- #
    #  pygame UI ヘルパー                                               #
    # ---------------------------------------------------------------- #

    def render_slot_list(
        self,
        surface,
        font,
        x: int = 20,
        y: int = 20,
        line_height: int = 32,
        color=(255, 255, 255),
        selected_slot=None,
        selected_color=(255, 220, 50),
    ) -> None:
        """
        セーブスロット一覧を pygame の Surface に描画する。

        Parameters
        ----------
        surface        : 描画先 pygame.Surface
        font           : pygame.font.Font
        x, y           : 描画開始座標
        line_height    : 行の高さ（px）
        color          : 通常テキスト色
        selected_slot  : 選択中スロット（強調表示）
        selected_color : 選択中の色

        Example
        -------
        font = pygame.font.SysFont(None, 28)
        mgr.render_slot_list(screen, font, selected_slot=current_slot)
        """
        try:
            import pygame
        except ImportError:
            raise ImportError("pygame が必要です: pip install pygame")

        slots = self.list()
        if not slots:
            text = font.render("セーブデータなし", True, color)
            surface.blit(text, (x, y))
            return

        for i, info in enumerate(slots):
            slot_id = info["slot"]
            saved   = info["saved_at"]
            pt      = self.format_play_time(info["play_time"])
            label   = f"[{slot_id:>8}]  {saved}  プレイ時間: {pt}"
            c = selected_color if str(slot_id) == str(selected_slot) else color
            text = font.render(label, True, c)
            surface.blit(text, (x, y + i * line_height))
