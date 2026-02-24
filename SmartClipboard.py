"""
SmartClipboard - 剪贴板历史管理工具

注意：此文件现在作为兼容层存在，代码已拆分到多个模块中。
请使用 main.py 作为新的入口点。
"""

# 重导出所有组件以保持向后兼容
from constants import *
from utils import *
from settings import SettingsManager
from database import DatabaseManager
from models import ClipboardModel

from core import (
    ImageCache, image_cache, get_cached_scaled_image,
    HotkeyHookWorker, WinHotkeyListener, WindowHistoryManager, AutoConfigManager
)

from ui import (
    get_settings_dialog_style, get_clipboard_card_style, get_context_menu_style,
    get_main_window_style, get_title_bar_style, get_message_box_style,
    get_tray_menu_style, get_search_bar_style,
    ClipboardDelegate, FloatingScrollBar, TitleBar, ClipboardCard,
    SettingsDialog, MainWindowUI, SmartClipboardApp
)

# 为了向后兼容，保留 main 函数
from main import main

if __name__ == "__main__":
    main()
