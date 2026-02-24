"""
UI components package
"""
from .styles import (
    get_settings_dialog_style, get_clipboard_card_style, get_context_menu_style,
    get_main_window_style, get_title_bar_style, get_message_box_style,
    get_tray_menu_style, get_search_bar_style
)
from .delegate import ClipboardDelegate
from .widgets import FloatingScrollBar, TitleBar, ClipboardCard
from .dialogs import SettingsDialog
from .main_window import MainWindowUI
from .main_app import SmartClipboardApp

__all__ = [
    # Styles
    'get_settings_dialog_style', 'get_clipboard_card_style', 'get_context_menu_style',
    'get_main_window_style', 'get_title_bar_style', 'get_message_box_style',
    'get_tray_menu_style', 'get_search_bar_style',
    # Components
    'ClipboardDelegate', 'FloatingScrollBar', 'TitleBar', 'ClipboardCard',
    'SettingsDialog', 'MainWindowUI', 'SmartClipboardApp'
]
