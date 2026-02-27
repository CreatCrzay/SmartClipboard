"""
UI Styles for SmartClipboard
"""
from constants import (
    COLOR_BACKGROUND, COLOR_CARD_BG, COLOR_TEXT_PRIMARY, COLOR_BUTTON_HOVER,
    COLOR_BORDER, COLOR_PINNED_BORDER, PADDING, SPACING, BORDER_RADIUS,
    BORDER_WIDTH, FONT_SIZE_TITLE, FONT_SIZE_CARD_CONTENT, FONT_SIZE_BUTTON,
    FONT_FAMILY_CHINESE, FONT_FAMILY_ENGLISH, CARD_INTERNAL_CONTENT_PADDING,
    SCROLLBAR_WIDTH
)


def get_settings_dialog_style():
    return f"""
        QDialog {{
            background-color: transparent;
            border: none;
        }}
        #settings_container {{
            background-color: {COLOR_BACKGROUND};
            border: 1px solid {COLOR_BORDER};
            border-radius: {BORDER_RADIUS}px;
        }}
        QCheckBox {{
            spacing: 5px;
            font-size: {FONT_SIZE_BUTTON};
            font-family: "{FONT_FAMILY_CHINESE}";
            color: {COLOR_TEXT_PRIMARY};
        }}
        QPushButton {{
            background-color: {COLOR_CARD_BG};
            color: {COLOR_TEXT_PRIMARY};
            border-radius: 4px;
            font-size: {FONT_SIZE_BUTTON};
        }}
        QPushButton:hover {{
            background-color: {COLOR_BUTTON_HOVER};
        }}
        QLabel {{
            color: {COLOR_TEXT_PRIMARY};
            font-size: {FONT_SIZE_BUTTON};
        }}
        QComboBox {{
            background-color: {COLOR_CARD_BG};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            border-radius: 3px;
            padding: 2px 5px;
            font-size: 12px;
            min-width: 60px;
        }}
        QComboBox:hover {{
            background-color: {COLOR_BUTTON_HOVER};
        }}
        QComboBox QAbstractItemView {{
            background-color: {COLOR_CARD_BG};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            border-radius: 3px;
            selection-background-color: {COLOR_BUTTON_HOVER};
            selection-color: {COLOR_TEXT_PRIMARY};
        }}
    """


def get_clipboard_card_style(is_pinned=False):
    bg_color = COLOR_CARD_BG
    border_style = f"{BORDER_WIDTH}px solid {COLOR_PINNED_BORDER}" if is_pinned else f"{BORDER_WIDTH}px solid transparent"
    return f"""
        QFrame {{
            background-color: {bg_color};
            border-radius: {BORDER_RADIUS}px;
            border: {border_style};
        }}
        QFrame:hover {{
            background-color: {COLOR_BUTTON_HOVER};
        }}
        QLabel {{
            background-color: transparent;
            color: {COLOR_TEXT_PRIMARY};
            font-size: {FONT_SIZE_CARD_CONTENT};
            font-family: "{FONT_FAMILY_ENGLISH}";
            padding: 0px;
            border: none;
        }}
    """


def get_context_menu_style():
    return f"""
        QMenu {{
            background-color: {COLOR_BACKGROUND};
            border: 1px solid {COLOR_BORDER};
            border-radius: {BORDER_RADIUS}px;
            padding: 5px;
        }}
        QMenu::item {{
            color: {COLOR_TEXT_PRIMARY};
            background-color: transparent;
            padding: 2px 15px;
            border-radius: 3px;
            margin: 2px 0;
        }}
        QMenu::item:selected {{
            background-color: {COLOR_BUTTON_HOVER};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QMenu::separator {{
            height: 1px;
            background: {COLOR_BORDER};
            margin: 5px 0;
        }}
    """


def get_main_window_style():
    return f"""
        QWidget#container_widget {{
            background-color: {COLOR_BACKGROUND};
            border-radius: {BORDER_RADIUS}px;
            border: {BORDER_WIDTH}px solid {COLOR_BORDER};
        }}
        QLabel {{
            color: {COLOR_TEXT_PRIMARY};
        }}
        QLabel[font-size="{FONT_SIZE_TITLE}"] {{
            font-size: {FONT_SIZE_TITLE};
            font-weight: bold;
        }}
        QPushButton {{
            background-color: {COLOR_CARD_BG};
            color: {COLOR_TEXT_PRIMARY};
            border-radius: {BORDER_RADIUS}px;
            padding: 5px 10px;
            font-size: {FONT_SIZE_BUTTON};
            font-family: "{FONT_FAMILY_ENGLISH}";
        }}
        QPushButton:hover {{
            background-color: {COLOR_BUTTON_HOVER};
        }}
        QScrollArea {{
            background-color: transparent;
            border: none;
        }}
        /* Floating scrollbar */
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: {SCROLLBAR_WIDTH}px;
            margin: 0px 0px 0px 0px;
            border-radius: {SCROLLBAR_WIDTH // 2}px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(80, 80, 80, 120);
            min-height: 20px;
            border-radius: {SCROLLBAR_WIDTH // 2}px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(120, 120, 120, 200);
        }}
        QScrollBar::handle:vertical:pressed {{
            background: rgba(150, 150, 150, 255);
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QWidget#cards_container {{
            background-color: {COLOR_BACKGROUND};
        }}
    """


def get_title_bar_style():
    return f"""
QWidget#title_bar {{
    background-color: {COLOR_BACKGROUND};
    border-top-left-radius: {BORDER_RADIUS}px;
    border-top-right-radius: {BORDER_RADIUS}px;
    border: none;
    border-bottom: {BORDER_WIDTH}px solid {COLOR_BORDER};
}}
QPushButton#settings_button, QPushButton#close_button {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT_PRIMARY};
    border: none;
    border-radius: 4px;
    font-size: 14px;
    font-family: "{FONT_FAMILY_CHINESE}";
    font-weight: bold;
    min-width: 32px;
    min-height: 20px;
    max-width: 32px;
    max-height: 20px;
}}
QPushButton#settings_button:hover, QPushButton#close_button:hover {{
    background-color: {COLOR_BUTTON_HOVER};
}}
"""


def get_message_box_style():
    return f"""
        QMessageBox {{
            background-color: {COLOR_BACKGROUND};
            border: 1px solid {COLOR_BORDER};
            border-radius: {BORDER_RADIUS}px;
        }}
        QMessageBox QLabel {{
            color: {COLOR_TEXT_PRIMARY};
            font-size: 13px;
        }}
        QMessageBox QPushButton {{
            background-color: {COLOR_CARD_BG};
            color: {COLOR_TEXT_PRIMARY};
            border-radius: {BORDER_RADIUS}px;
            padding: 5px 15px;
            font-size: 12px;
            min-width: 30px;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {COLOR_BUTTON_HOVER};
        }}
        QMessageBox QPushButton:pressed {{
            background-color: #606060;
        }}
    """


def get_tray_menu_style():
    return f"""
        QMenu {{
            background-color: {COLOR_BACKGROUND};
            border: 1px solid {COLOR_BORDER};
            border-radius: {BORDER_RADIUS}px;
            padding: 5px;
        }}
        QMenu::item {{
            color: {COLOR_TEXT_PRIMARY};
            background-color: transparent;
            padding: 5px 15px;
            border-radius: 3px;
            margin: 2px 0;
        }}
        QMenu::item:selected {{
            background-color: {COLOR_BUTTON_HOVER};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QMenu::separator {{
            height: 1px;
            background: {COLOR_BORDER};
            margin: 5px 0;
        }}
    """


def get_search_bar_style():
    return f"""
        QLineEdit {{
            background-color: {COLOR_CARD_BG};
            color: {COLOR_TEXT_PRIMARY};
            border: none;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
            font-family: "{FONT_FAMILY_ENGLISH}";
        }}
        QLineEdit:focus {{
            border: none;
        }}
        QLineEdit:placeholder {{
            color: #888888;
        }}
    """
