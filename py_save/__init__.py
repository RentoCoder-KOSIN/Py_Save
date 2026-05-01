"""
py_save  –  ゲーム向けセーブデータ管理ライブラリ

基本使い方:
    from py_save import SaveManager
    from py_save import PygameSaveManager   # pygame 連携版
"""

from .save_manager import SaveManager, SaveError, SlotNotFoundError, SlotAlreadyExistsError
from .pygame_save import PygameSaveManager

__all__ = [
    "SaveManager",
    "PygameSaveManager",
    "SaveError",
    "SlotNotFoundError",
    "SlotAlreadyExistsError",
]

__version__ = "1.0.0"
__author__  = "RentoCoder-KOSIN"
