import sys
import os
import json
import hashlib
import datetime
import shutil
import base64
import logging
import sqlite3
import re
import time
import threading
import ctypes
import subprocess
from ctypes import wintypes
from collections import deque, OrderedDict
from threading import Lock
from pathlib import Path

# PySide6 Imports
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMessageBox, QFileDialog, QDialog, QStyle, QMenu,
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton, QScrollArea,
    QFrame, QCheckBox, QSizePolicy, QComboBox, QSpinBox, QListView, QStyledItemDelegate,
    QLineEdit
)
from PySide6.QtGui import (
    QAction, QIcon, QImage, QCursor, QPainter, QColor, QKeySequence,
    QPixmap, QFont, QFontMetrics, QPen, QKeyEvent
)
from PySide6.QtCore import (
    Signal, QTimer, QByteArray, QMimeData, QUrl, QBuffer, QObject, Qt,
    QPoint, QFileInfo, QThread, QRunnable, QThreadPool, QMetaObject, Q_ARG,
    QAbstractListModel, QModelIndex, QSize, QItemSelectionModel, QSortFilterProxyModel,
    QEvent
)

# Third-party Imports
import html2text
from pynput.keyboard import Controller

# Optional Windows Imports
try:
    import win32gui
    import win32con
    import win32process
except ImportError:
    win32gui = None
    win32con = None
    win32process = None

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# ============================================================
# Section: Constants
# ============================================================

COLOR_BACKGROUND = "#1E1E1E"
COLOR_CARD_BG = "#282828"
COLOR_TEXT_PRIMARY = "#FFFFFF"

COLOR_BUTTON_HOVER = "#505050"
COLOR_BORDER = "#404040"
COLOR_PINNED_BORDER = "#FFFFFF" 

WINDOW_WIDTH = 300
WINDOW_HEIGHT = 400

PADDING_LEFT = 6
PADDING_RIGHT = 3

PADDING_TOP = 5
PADDING_BOTTOM = 12
SPACING = 5
BORDER_RADIUS = 0
BORDER_WIDTH = 1

CARD_INTERNAL_CONTENT_PADDING = 5
CARD_INTERNAL_SPACING = 5
CARD_HEIGHT_FIXED = 78 

SCROLLBAR_WIDTH = 3
SCROLLBAR_SPACING = 5

CARD_WIDTH_FIXED = WINDOW_WIDTH - PADDING_LEFT - PADDING_RIGHT - (BORDER_WIDTH * 2) - (SCROLLBAR_WIDTH + SCROLLBAR_SPACING) 

FONT_SIZE_TITLE = "15px"
FONT_SIZE_CARD_CONTENT = "15px"
FONT_SIZE_BUTTON = "13px"

FONT_FAMILY_ENGLISH = "Consolas"
FONT_FAMILY_CHINESE = "微软雅黑"

ICON_FILE = "📁"  # 文件类型卡片显示的文件图标

DATABASE_NAME = "smartclipboard.db"
SETTINGS_FILE = "settings.json"
TEMP_DIR_NAME = "temp"


# ============================================================
# Section: Utils (Resource, File, Image Cache)
# ============================================================

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_app_data_path():
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return application_path

def get_file_metadata_hash(file_path):
    try:
        is_dir = os.path.isdir(file_path)
        stat = os.stat(file_path)
        metadata = {
            "name": os.path.basename(file_path),
            "path": os.path.normpath(file_path), 
            "size": stat.st_size if not is_dir else 0,
            "mtime": stat.st_mtime,
            "is_dir": is_dir
        }
        metadata_str = json.dumps(metadata, sort_keys=True, separators=(',', ':'))
        return hashlib.md5(metadata_str.encode('utf-8')).hexdigest()
    except (OSError, IOError):
        return hashlib.md5(os.path.normpath(file_path).encode('utf-8')).hexdigest()

class ClipboardModel(QAbstractListModel):
    """剪贴板数据模型 (Qt Model)"""
    
    # 自定义角色枚举
    RoleId = Qt.UserRole + 1
    RoleType = Qt.UserRole + 2
    RoleContent = Qt.UserRole + 3
    RoleIsPinned = Qt.UserRole + 4
    RoleContentPreview = Qt.UserRole + 5
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._clips = []  # 存储 (id, type, content, is_pinned) 元组
        self._id_to_row = {}  # id -> row 索引映射，用于快速查找
    
    def rowCount(self, parent=None):
        return len(self._clips)
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._clips):
            return None
        
        clip = self._clips[index.row()]
        clip_id, clip_type, clip_content, is_pinned = clip
        
        if role == Qt.DisplayRole:
            # 默认显示：显示类型
            return f"[{clip_type}]"
        elif role == self.RoleId:
            return clip_id
        elif role == self.RoleType:
            return clip_type
        elif role == self.RoleContent:
            return clip_content
        elif role == self.RoleIsPinned:
            return is_pinned
        elif role == self.RoleContentPreview:
            return self._get_content_preview(clip_type, clip_content)
        
        return None
    
    def roleNames(self):
        return {
            Qt.DisplayRole: b"display",
            self.RoleId: b"clip_id",
            self.RoleType: b"clip_type",
            self.RoleContent: b"clip_content",
            self.RoleIsPinned: b"is_pinned",
            self.RoleContentPreview: b"content_preview",
        }
    
    def _get_content_preview(self, clip_type, content):
        """获取内容的预览文本"""
        try:
            if clip_type == "TEXT":
                preview = content.replace('\n', ' ').strip()
                return preview[:50] + ('...' if len(preview) > 50 else '')
            elif clip_type == "IMAGE":
                return "[图像]"
            elif clip_type == "FILES":
                data = json.loads(content)
                paths = data.get("original_paths", [])
                if paths:
                    return os.path.basename(paths[0]) + ('...' if len(paths) > 1 else '')
                return "[文件]"
            else:
                return str(content)[:50]
        except:
            return "[内容]"
    
    def set_data_list(self, clips):
        """
        设置新的数据列表
        clips: [(id, type, content, is_pinned), ...]
        """
        self.beginResetModel()
        self._clips = clips
        self._id_to_row = {clip[0]: i for i, clip in enumerate(clips)}
        self.endResetModel()
    
    def get_clip_by_id(self, clip_id):
        """根据 ID 获取 clip 数据"""
        row = self._id_to_row.get(clip_id)
        if row is not None and row < len(self._clips):
            return self._clips[row]
        return None
    
    def get_row_by_id(self, clip_id):
        """根据 ID 获取行索引"""
        return self._id_to_row.get(clip_id)
    
    def remove_row_by_id(self, clip_id):
        """根据 ID 删除行"""
        row = self._id_to_row.get(clip_id)
        if row is not None:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._clips[row]
            # 重新构建 id -> row 映射
            self._id_to_row = {clip[0]: i for i, clip in enumerate(self._clips)}
            self.endRemoveRows()
            return True
        return False
    
    def update_row_by_id(self, clip_id):
        """触发某行的数据更新信号"""
        row = self._id_to_row.get(clip_id)
        if row is not None:
            index = self.index(row)
            self.dataChanged.emit(index, index)


class ImageCache:
    def __init__(self, max_size=50):
        self.max_size = max_size
        self._cache = OrderedDict()
        self._lock = Lock()
        
    def get(self, key):
        with self._lock:
            if key in self._cache:
                value = self._cache.pop(key)
                self._cache[key] = value
                return value
            return None
    
    def put(self, key, pixmap):
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            self._cache[key] = pixmap
    
    def clear(self):
        with self._lock:
            self._cache.clear()
    
    def get_cache_key(self, image_data_b64, width, height):
        data_hash = hashlib.md5(image_data_b64.encode('utf-8')).hexdigest()
        return f"{data_hash}_{width}x{height}"

# Global image cache instance
image_cache = ImageCache()

def get_cached_scaled_image(image_data_b64, width, height):
    """获取缓存的缩放图像"""
    cache_key = image_cache.get_cache_key(image_data_b64, width, height)
    cached_pixmap = image_cache.get(cache_key)
    if cached_pixmap:
        return cached_pixmap
    
    try:
        image_data = QByteArray.fromBase64(image_data_b64.encode('utf-8'))
        image = QImage()
        if image.loadFromData(image_data):
            original_pixmap = QPixmap.fromImage(image)
            scaled_pixmap = original_pixmap.scaled(
                width, height,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            image_cache.put(cache_key, scaled_pixmap)
            return scaled_pixmap
    except Exception as e:
        print(f"Error processing image: {e}")
    return None


class ClipboardDelegate(QStyledItemDelegate):
    """剪贴板项委托 (Qt Delegate) - 自定义列表项渲染"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = QFont(FONT_FAMILY_ENGLISH)
        self._font.setPixelSize(int(FONT_SIZE_CARD_CONTENT.replace('px', '')))
    
    def paint(self, painter, option, index):
        # 绘制背景
        is_pinned = index.data(ClipboardModel.RoleIsPinned)
        
        # 设置背景色
        bg_color = QColor(COLOR_CARD_BG)
        if option.state & QStyle.State_Selected:
            bg_color = QColor(COLOR_BUTTON_HOVER)
        elif option.state & QStyle.State_MouseOver:
            bg_color = QColor(COLOR_BUTTON_HOVER)
        
        painter.fillRect(option.rect, bg_color)
        
        # 绘制边框（置顶项目）
        if is_pinned:
            pen = QPen(QColor(COLOR_PINNED_BORDER))
            pen.setWidth(BORDER_WIDTH)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(0, 0, -BORDER_WIDTH, -BORDER_WIDTH))
        
        # 获取数据
        clip_type = index.data(ClipboardModel.RoleType)
        content = index.data(ClipboardModel.RoleContent)
        
        # 绘制内容
        self._draw_content(painter, option, clip_type, content)
    
    def _draw_content(self, painter, option, clip_type, content):
        """根据类型绘制内容"""
        # 计算内容绘制区域的起始坐标和可用宽高
        x = option.rect.left() + CARD_INTERNAL_CONTENT_PADDING
        y = option.rect.top() + CARD_INTERNAL_CONTENT_PADDING
        
        # 减去滚动条宽度和左右Padding
        available_width = option.rect.width() - (CARD_INTERNAL_CONTENT_PADDING * 2) - (SCROLLBAR_WIDTH + SCROLLBAR_SPACING)
        # 减去上下Padding
        available_height = option.rect.height() - (CARD_INTERNAL_CONTENT_PADDING * 2)
        
        try:
            if clip_type == "TEXT":
                # 传入 available_height
                self._draw_text(painter, x, y, available_width, available_height, content)
            elif clip_type == "IMAGE":
                # 传入 available_height
                self._draw_image(painter, x, y, available_width, available_height, content)
            elif clip_type == "FILES":
                # 传入 available_height
                self._draw_files(painter, x, y, available_width, available_height, content)
            else:
                self._draw_text(painter, x, y, available_width, available_height, str(content)[:50])
        except Exception as e:
            self._draw_text(painter, x, y, available_width, available_height, "[渲染错误]")
    
    def _draw_text(self, painter, x, y, max_width, max_height, text):
        """绘制文本内容（垂直居中）"""
        painter.setFont(self._font)
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))
        
        if not text.strip():
            text = "(无内容)"
        
        metrics = QFontMetrics(self._font)
        lines = text.split('\n')
        line_height = metrics.lineSpacing()
        
        # 1. 确定要绘制的行数（最多3行）
        max_lines = 3
        display_lines = lines[:max_lines]
        
        # 2. 计算文本块的总高度
        total_text_height = len(display_lines) * line_height
        
        # 3. 计算垂直居中的起始 Y 坐标偏移量
        y_offset = (max_height - total_text_height) // 2
        y_offset = max(0, y_offset) # 确保不为负
        
        current_y = y + y_offset
        
        # 4. 循环绘制
        for i, line in enumerate(display_lines):
            # 如果文字高度溢出则停止（一般不会，因为限制了3行）
            if (i + 1) * line_height > max_height:
                break
                
            elided = metrics.elidedText(line, Qt.ElideRight, max_width)
            # drawText 的 y 坐标是基线(Baseline)，需要计算：Top + 行高 - descent
            baseline_y = current_y + (i + 1) * line_height - metrics.descent()
            painter.drawText(x, int(baseline_y), elided)
    
    def _draw_image(self, painter, x, y, max_width, max_height, content):
        """绘制图像缩略图（水平+垂直居中）"""
        try:
            image_data_b64 = content
            if isinstance(content, dict):
                image_data_b64 = content.get("image_data", content)
            elif isinstance(content, str):
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        image_data_b64 = data.get("image_data", content)
                except:
                    pass
            
            cached_pixmap = get_cached_scaled_image(image_data_b64, max_width, max_height)
            if cached_pixmap:
                # 保持比例缩放
                pixmap = cached_pixmap.scaled(
                    max_width, max_height,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                
                # 计算居中坐标
                draw_x = x   # 水平居中
                draw_y = y + (max_height - pixmap.height()) // 2 # 垂直居中
                
                painter.drawPixmap(draw_x, draw_y, pixmap)
            else:
                # 图片加载中或失败时的文字提示，也让它居中
                text = "加载中..."
                metrics = QFontMetrics(self._font)
                text_width = metrics.horizontalAdvance(text)
                text_height = metrics.height()
                
                draw_x = x + (max_width - text_width) // 2
                draw_y = y + (max_height + text_height) // 2 - metrics.descent()
                
                painter.setFont(self._font)
                painter.setPen(QColor(COLOR_TEXT_PRIMARY))
                painter.drawText(draw_x, int(draw_y), text)

        except Exception as e:
            painter.setFont(self._font)
            painter.setPen(QColor(COLOR_TEXT_PRIMARY))
            painter.drawText(x, y + 20, "[图像加载失败]")
    
    def _draw_files(self, painter, x, y, max_width, max_height, content):
        """绘制文件列表（垂直居中）"""
        painter.setFont(self._font)
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))
        
        try:
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = content
            
            original_paths = data.get("original_paths", [])
            if not original_paths:
                painter.drawText(x, y + 20, f"{ICON_FILE} (无文件)")
                return
            
            metrics = QFontMetrics(self._font)
            line_height = metrics.lineSpacing()
            
            # 1. 准备文本内容
            first_path = original_paths[0]
            first_filename = os.path.basename(first_path)
            first_folder = os.path.dirname(first_path)
            file_count = len(original_paths)
            
            if file_count == 1:
                first_line = f"{ICON_FILE} {first_filename}"
            else:
                count_text = f" (+{file_count - 1} 个文件)"
                first_line = f"{ICON_FILE} {first_filename}{count_text}"
            
            # 2. 计算两行文本的总高度
            total_height = line_height * 2
            
            # 3. 计算垂直居中偏移
            y_offset = (max_height - total_height) // 2
            y_offset = max(0, y_offset)
            current_y = y + y_offset
            
            # 4. 绘制第一行 (文件名)
            elided_filename = metrics.elidedText(first_line, Qt.ElideRight, max_width)
            baseline_1 = current_y + line_height - metrics.descent()
            painter.drawText(x, int(baseline_1), elided_filename)
            
            # 5. 绘制第二行 (文件夹路径)
            ellipsis_text = "..."
            ellipsis_width = metrics.horizontalAdvance(ellipsis_text)
            folder_text_width = max_width - ellipsis_width - 5
            folder_elided = metrics.elidedText(first_folder, Qt.ElideMiddle, folder_text_width)
            
            baseline_2 = current_y + 2 * line_height - metrics.descent()
            painter.drawText(x, int(baseline_2), folder_elided)
            
        except Exception as e:
            painter.drawText(x, y + 20, f"{ICON_FILE} [解析错误]")
    
    def sizeHint(self, option, index):
        return QSize(CARD_WIDTH_FIXED, CARD_HEIGHT_FIXED)


# ============================================================
# Section: Styles
# ============================================================

def get_settings_dialog_style():
    return f"""
        QDialog {{
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
        QScrollBar:vertical {{
            border: none;
            background: {COLOR_BACKGROUND};
            width: {SCROLLBAR_WIDTH}px;
            margin: 0px 0px 0px 0px;
            border-radius: {BORDER_RADIUS // 2}px;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_BUTTON_HOVER};
            min-height: 20px;
            border-radius: {BORDER_RADIUS // 2}px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
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
            border-radius: 0px;
            font-size: 14px;
            font-weight: bold;
            min-width: 40px;
            min-height: 24px;
            max-width: 40px;
            max-height: 24px;
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
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
            font-family: "{FONT_FAMILY_ENGLISH}";
        }}
        QLineEdit:focus {{
            border: 1px solid {COLOR_BUTTON_HOVER};
        }}
        QLineEdit:placeholder {{
            color: #888888;
        }}
    """


# ============================================================
# Section: Settings
# ============================================================

class SettingsManager:
    def __init__(self, current_dir):
        self.current_dir = current_dir
        self.settings_file = os.path.join(current_dir, SETTINGS_FILE)
        self.default_settings = {
            "auto_clean_days": 7,
            "auto_clean_enabled": False,
            "window_width": 270,
            "window_height": 390,
            "paste_as_file_enabled": False,
            "max_history_enabled": True,
            "max_history_count": 100,
            "create_copy_enabled": False,
        }
        self.settings = self.load_settings()
    
    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    merged_settings = self.default_settings.copy()
                    merged_settings.update(settings)
                    for key, default_value in self.default_settings.items():
                        if key not in merged_settings:
                            merged_settings[key] = default_value
                    return merged_settings
            else:
                self.save_settings(self.default_settings)
                return self.default_settings.copy()
        except (OSError, IOError, json.JSONDecodeError):
            return self.default_settings.copy()
    
    def save_settings(self, settings):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            self.settings = settings
        except (OSError, IOError, TypeError):
            pass
    
    def get(self, key, default=None):
        return self.settings.get(key, default)
    
    def set(self, key, value):
        self.settings[key] = value
        self.save_settings(self.settings)


# ============================================================
# Section: Database
# ============================================================

class DatabaseManager:
    def __init__(self, current_dir):
        self.db_path = os.path.join(current_dir, DATABASE_NAME)
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_table()
        self._add_is_pinned_column()

    def _connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            logging.info(f"DatabaseManager: Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error connecting to database {self.db_path}: {e}")

    def _create_table(self):
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_pinned BOOLEAN DEFAULT FALSE
                )
            """)
            self.conn.commit()
            logging.info("DatabaseManager: Table 'clips' ensured.")
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error creating table 'clips': {e}")

    def _add_is_pinned_column(self):
        try:
            self.cursor.execute("SELECT is_pinned FROM clips LIMIT 1")
            logging.debug("DatabaseManager: 'is_pinned' column already exists.")
        except sqlite3.OperationalError:
            try:
                self.cursor.execute("ALTER TABLE clips ADD COLUMN is_pinned BOOLEAN DEFAULT FALSE")
                self.conn.commit()
                logging.info("DatabaseManager: Added 'is_pinned' column to 'clips' table.")
            except sqlite3.Error as e:
                logging.error(f"DatabaseManager: Error adding 'is_pinned' column: {e}")

    def add_clip(self, clip_type, content, is_pinned=False):
        try:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute(
                "INSERT INTO clips (type, content, timestamp, is_pinned) VALUES (?, ?, ?, ?)",
                (clip_type, content, current_time, is_pinned)
            )
            self.conn.commit()
            new_id = self.cursor.lastrowid
            logging.info(f"DatabaseManager: Clip added with ID: {new_id}, Type: {clip_type}")
            return new_id
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error adding clip (Type: {clip_type}, Content: {content[:100]}...): {e}")
            return None

    def update_clip_content(self, clip_id, new_content):
        try:
            self.cursor.execute("UPDATE clips SET content = ? WHERE id = ?", (new_content, clip_id))
            self.conn.commit()
            logging.info(f"DatabaseManager: Clip ID {clip_id} content updated successfully.")
            return True
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error updating clip ID {clip_id} content: {e}")
            return False

    def update_clip_type(self, clip_id, new_type):
        try:
            self.cursor.execute("UPDATE clips SET type = ? WHERE id = ?", (new_type, clip_id))
            self.conn.commit()
            logging.info(f"DatabaseManager: Clip ID {clip_id} type updated to {new_type} successfully.")
            return True
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error updating clip ID {clip_id} type: {e}")
            return False

    def get_all_clips(self):
        try:
            self.cursor.execute("SELECT id, type, content, is_pinned FROM clips ORDER BY is_pinned DESC, timestamp DESC")
            clips = self.cursor.fetchall()
            logging.debug(f"DatabaseManager: Fetched {len(clips)} clips.")
            return clips
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error fetching all clips: {e}")
            return []

    def delete_clip(self, clip_id):
        try:
            self.cursor.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logging.info(f"DatabaseManager: Clip ID {clip_id} deleted successfully.")
                return True
            else:
                logging.warning(f"DatabaseManager: Clip ID {clip_id} not found for deletion.")
                return False
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error deleting clip ID {clip_id}: {e}")
            return False

    def delete_all_clips(self):
        try:
            self.cursor.execute("DELETE FROM clips WHERE is_pinned = FALSE")
            self.conn.commit()
            deleted_count = self.cursor.rowcount
            logging.info(f"DatabaseManager: Deleted {deleted_count} unpinned clips.")
            return deleted_count > 0
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error deleting all unpinned clips: {e}")
            return False

    def delete_old_clips(self, days):
        try:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            cutoff_date_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute("DELETE FROM clips WHERE timestamp < ? AND is_pinned = FALSE", (cutoff_date_str,))
            deleted_count = self.cursor.rowcount
            self.conn.commit()
            logging.info(f"DatabaseManager: Deleted {deleted_count} old unpinned clips.")
            return deleted_count
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error deleting old clips: {e}")
            return 0

    def toggle_pin_status(self, clip_id, is_pinned):
        try:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute(
                "UPDATE clips SET is_pinned = ?, timestamp = ? WHERE id = ?",
                (is_pinned, current_time, clip_id)
            )
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logging.info(f"DatabaseManager: Clip ID {clip_id} pin status toggled to {is_pinned}.")
                return True
            else:
                logging.warning(f"DatabaseManager: Clip ID {clip_id} not found for pin toggle.")
                return False
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error toggling pin status for clip ID {clip_id}: {e}")
            return False

    def update_clip_timestamp(self, clip_id):
        try:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute(
                "UPDATE clips SET timestamp = ? WHERE id = ?",
                (current_time, clip_id)
            )
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logging.info(f"DatabaseManager: Clip ID {clip_id} timestamp updated successfully.")
                return True
            else:
                logging.warning(f"DatabaseManager: Clip ID {clip_id} not found for timestamp update.")
                return False
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error updating timestamp for clip ID {clip_id}: {e}")
            return False

    def enforce_max_history(self, max_count):
        deleted_clip_ids = []
        try:
            self.cursor.execute("SELECT COUNT(*) FROM clips WHERE is_pinned = FALSE")
            unpinned_clips_count = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT COUNT(*) FROM clips WHERE is_pinned = TRUE")
            pinned_clips_count = self.cursor.fetchone()[0]
            effective_max_unpinned_count = max(0, max_count - pinned_clips_count)

            if unpinned_clips_count <= effective_max_unpinned_count:
                return deleted_clip_ids
            num_to_delete = unpinned_clips_count - effective_max_unpinned_count
            logging.info(f"DatabaseManager: Unpinned clips ({unpinned_clips_count}) exceeds effective max ({effective_max_unpinned_count}). Will attempt to delete {num_to_delete} oldest unpinned clips.")
            for _ in range(num_to_delete):
                self.cursor.execute(
                    "SELECT id FROM clips WHERE is_pinned = FALSE ORDER BY timestamp ASC LIMIT 1"
                )
                oldest_unpinned_clip = self.cursor.fetchone()
                if oldest_unpinned_clip:
                    clip_id_to_delete = oldest_unpinned_clip[0]
                    if self.delete_clip(clip_id_to_delete):
                        deleted_clip_ids.append(clip_id_to_delete)
                    else:
                        logging.warning(f"DatabaseManager: Failed to delete oldest unpinned clip ID {clip_id_to_delete}.")
                        break
                else:
                    logging.info("DatabaseManager: No more unpinned clips to delete to enforce max history.")
                    break
            if deleted_clip_ids:
                logging.info(f"DatabaseManager: Enforced max history. Deleted clip IDs: {deleted_clip_ids}")
            return deleted_clip_ids

        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error enforcing max history: {e}")
            return []

    def close(self):
        if self.conn:
            try:
                self.conn.close()
                logging.info("DatabaseManager: Database connection closed.")
            except sqlite3.Error as e:
                logging.warning(f"DatabaseManager: Error closing database connection: {e}")


# ============================================================
# Section: Windows Internals (Hotkey, History, AutoStart)
# ============================================================

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_V = 0x56
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
    ]

class HotkeyHookWorker(QThread):
    hotkey_triggered = Signal()
    
    def __init__(self):
        super().__init__()
        self.hook = None
        self.hook_proc = None
        self._running = True
        self._v_pressed = False  # 新增：用于防抖和防止自动重复
        # 定义虚拟键码
        self.VK_V = 0x56
        self.VK_LWIN = 0x5B
        self.VK_RWIN = 0x5C
        # 使用 0xFF 作为欺骗键，它通常未被定义，不会触发 Ctrl 相关的快捷键
        self.VK_DUMMY = 0xFF 

    def run(self):
        self._setup_hook()
        msg = wintypes.MSG()
        while self._running:
            try:
                # 使用 PeekMessage 保持消息循环，防止界面卡顿
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                break
            time.sleep(0.005)
    
    def _setup_hook(self):
        self.hook_proc = HOOKPROC(self._keyboard_hook_proc)
        self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.hook_proc, 0, 0)
    
    def _send_dummy_key(self):
        """
        发送一个无意义的按键事件 (0xFF)。
        目的：欺骗 Windows，让它认为 Win 键处于组合键状态，
        从而在 Win 键松开时不要弹出开始菜单。
        相比 Ctrl，0xFF 不会触发 PowerToys 或输入法切换。
        """
        try:
            # keybd_event 参数: (bVk, bScan, dwFlags, dwExtraInfo)
            # 0 = KeyDown, 2 = KeyUp
            user32.keybd_event(self.VK_DUMMY, 0, 0, 0) # Dummy Down
            user32.keybd_event(self.VK_DUMMY, 0, 2, 0) # Dummy Up
        except Exception:
            pass

    def _keyboard_hook_proc(self, nCode, wParam, lParam):
        try:
            if nCode >= 0:
                kb_data = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk_code = kb_data.vkCode
                
                # 检测消息类型
                is_down = (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN)
                is_up = (wParam == WM_KEYUP or wParam == WM_SYSKEYUP)

                # 处理 V 键
                if vk_code == self.VK_V:
                    if is_down:
                        # 检查 Win 键是否被按下
                        win_pressed = (user32.GetAsyncKeyState(self.VK_LWIN) & 0x8000 != 0) or \
                                      (user32.GetAsyncKeyState(self.VK_RWIN) & 0x8000 != 0)
                        
                        if win_pressed:
                            # 核心逻辑：如果是第一次按下（不是按住不放产生的重复）
                            if not self._v_pressed:
                                self._v_pressed = True
                                self._send_dummy_key() # 抑制开始菜单
                                self.hotkey_triggered.emit() # 触发业务逻辑
                            
                            # 无论是否重复，都拦截 V 键，防止输入到前台窗口
                            return 1
                            
                    elif is_up:
                        # V 键松开，重置状态，允许下一次触发
                        # 这里我们只拦截我们处理过的 V 键
                        if self._v_pressed:
                            self._v_pressed = False
                            return 1

        except Exception:
            pass
        return user32.CallNextHookEx(self.hook, nCode, wParam, lParam)
    
    def stop_hook(self):
        self._running = False
        if self.hook:
            user32.UnhookWindowsHookEx(self.hook)
            self.hook = None

class WinHotkeyListener(QObject):
    hotkeyPressed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._is_listening = False
    
    def start_listening(self):
        if not self._is_listening:
            self.worker = HotkeyHookWorker()
            self.worker.hotkey_triggered.connect(self._on_hotkey_pressed)
            self.worker.start()
            self._is_listening = True
    
    def stop_listening(self):
        if self._is_listening and self.worker:
            self.worker.hotkey_triggered.disconnect()
            self.worker.stop_hook()
            self.worker.quit()
            self.worker.wait(3000)
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()
            self.worker = None
            self._is_listening = False
    
    def _on_hotkey_pressed(self):
        self.hotkeyPressed.emit()

class WindowHistoryManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hwnd_history = deque(maxlen=4)
        self._last_hwnd = None
        self._app_main_window_hwnd = None

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._update_window_history)
        self._win32gui = None
        self._win32process = None
        if sys.platform == "win32":
            try:
                import win32gui
                import win32process
                self._win32gui = win32gui
                self._win32process = win32process
                logging.info("WindowHistoryManager: win32gui and win32process loaded.")
            except ImportError:
                pass
        self._system_window_classes = {
            "Shell_TrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow",
            "ApplicationFrameWindow", "TopLevelWindowForOverflowXamlIsland",
            "Qt5QWindowIcon", "Qt5QWindowOwnDCIcon", "SmartClipboard"
        }
        if parent and self._win32gui:
            try:
                self._app_main_window_hwnd = int(parent.winId())
            except Exception as e:
                self._app_main_window_hwnd = None
        
    def start_tracking(self):
        if self._win32gui:
            self._timer.start()
    
    def stop_tracking(self):
        self._timer.stop()
    
    def _get_window_title_and_process(self, hwnd):
        try:
            if self._win32gui and self._win32process:
                title = self._win32gui.GetWindowText(hwnd)
                _, pid = self._win32process.GetWindowThreadProcessId(hwnd)
                return title, pid
        except Exception:
            pass
        return "", 0
    
    def _get_window_class_name(self, hwnd):
        try:
            if self._win32gui:
                return self._win32gui.GetClassName(hwnd)
        except Exception:
            pass
        return ""
    
    def _is_valid_app_window(self, hwnd):
        if not self._win32gui or not hwnd:
            return False
        try:
            if not self._win32gui.IsWindowVisible(hwnd) or self._win32gui.IsIconic(hwnd):
                return False
            if hwnd == self._app_main_window_hwnd:
                return False
            class_name = self._get_window_class_name(hwnd)
            if class_name in self._system_window_classes:
                return False
            title = self._win32gui.GetWindowText(hwnd)
            if not title:
                return False
            if class_name.startswith("Qt") and not title:
                return False
            return True
        except Exception as e:
            return False
    
    def _update_window_history(self):
        if not self._win32gui:
            return
        try:
            current_hwnd = self._win32gui.GetForegroundWindow()
            if current_hwnd and current_hwnd != self._last_hwnd:
                if self._is_valid_app_window(current_hwnd):
                    self._last_hwnd = current_hwnd
                    self._hwnd_history.append(current_hwnd)
                else:
                    self._last_hwnd = current_hwnd
        except Exception as e:
            pass
    
    def restore_to_earliest_window(self):
        if not self._win32gui:
            return
        for i in range(len(self._hwnd_history) - 1, -1, -1):
            hwnd_to_restore = self._hwnd_history[i]
            try:
                if self._win32gui.IsWindow(hwnd_to_restore) and self._is_valid_app_window(hwnd_to_restore):
                    if self._win32gui.IsIconic(hwnd_to_restore):
                        self._win32gui.ShowWindow(hwnd_to_restore, 9)
                    else:
                        self._win32gui.ShowWindow(hwnd_to_restore, 5)
                    self._win32gui.SetForegroundWindow(hwnd_to_restore)
                    return
            except Exception as e:
                continue

class AutoConfigManager:
    """自动配置自启动管理器"""
    def __init__(self):
        self.app_data_dir = get_app_data_path()
        self.config_file = os.path.join(self.app_data_dir, "auto_config.json")
        self.ensure_app_data_dir()
        
    def ensure_app_data_dir(self):
        try:
            os.makedirs(self.app_data_dir, exist_ok=True)
        except (OSError, IOError) as e:
            pass
    
    def is_first_run(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return not config.get('first_run_completed', False)
            else:
                return True
        except (OSError, IOError, json.JSONDecodeError):
            return True
    
    def mark_first_run_completed(self):
        try:
            config = {'first_run_completed': True}
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except (OSError, IOError):
            pass
    
    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    
    def run_as_admin_and_exit(self):
        if not self.is_admin():
            try:
                script = os.path.abspath(sys.argv[0])
                params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, f'"{script}"', params, 1
                )
                sys.exit(0)
            except Exception as e:
                sys.exit(1)
    
    def create_scheduled_task(self):
        if not self.is_admin():
            return False
        
        if getattr(sys, 'frozen', False):
            app_exe_path = sys.executable
        else:
            app_exe_path = os.path.abspath(sys.argv[0])
        
        if not os.path.exists(app_exe_path):
            return False
        
        current_user = os.getlogin()
        task_name = "SmartClipboardAutostart"
        
        subprocess.run(['schtasks', '/delete', '/tn', task_name, '/f'], capture_output=True, encoding='gbk')
        
        command = [
            'schtasks', '/create', '/tn', task_name, '/tr', f'"{app_exe_path}"',
            '/sc', 'ONLOGON', '/ru', current_user, '/rl', 'HIGHEST', '/it', '/f'
        ]
        
        try:
            subprocess.run(command, capture_output=True, text=True, encoding='gbk', check=True)
            return True
        except Exception:
            return False
    
    def setup_auto_start(self):
        if not self.is_first_run():
            return True
        self.run_as_admin_and_exit()
        success = self.create_scheduled_task()
        if success:
            self.mark_first_run_completed()
            return True
        else:
            return False


# ============================================================
# Section: UI Widgets
# ============================================================

class TitleBar(QWidget):
    settings_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("title_bar")
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(BORDER_WIDTH, BORDER_WIDTH, BORDER_WIDTH, BORDER_WIDTH)
        layout.setSpacing(0)

        self.settings_button = QPushButton("设置")
        button_font = QFont(FONT_FAMILY_CHINESE)
        button_font.setPixelSize(int(FONT_SIZE_BUTTON.replace('px', '')))
        button_font.setBold(True)
        self.settings_button.setFont(button_font)
        self.settings_button.setFixedSize(40, 24)
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self.settings_button.setObjectName("settings_button")

        self.close_button = QPushButton("关闭")
        close_font = QFont(FONT_FAMILY_CHINESE)
        close_font.setPixelSize(int(FONT_SIZE_BUTTON.replace('px', '')))
        close_font.setBold(True)
        self.close_button.setFont(close_font)
        self.close_button.setFixedSize(40, 24)
        self.close_button.clicked.connect(self.close_requested.emit)
        self.close_button.setObjectName("close_button")

        layout.addWidget(self.settings_button)
        layout.addStretch(1)
        layout.addWidget(self.close_button)
        
        self.setStyleSheet(get_title_bar_style())

class ClipboardCard(QFrame):
    card_clicked = Signal(int, str, object)
    card_export = Signal(int)
    card_delete = Signal(int)
    card_pin_toggled = Signal(int)

    def __init__(self, clip_id, clip_type, clip_content, is_pinned=False, parent=None):
        super().__init__(parent)
        self.clip_id = clip_id
        self.clip_type = clip_type
        self.clip_content = clip_content
        self._is_pinned = is_pinned 

        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(CARD_HEIGHT_FIXED)
        self.setFixedWidth(CARD_WIDTH_FIXED)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._font = QFont(FONT_FAMILY_ENGLISH)
        self._font.setPixelSize(int(FONT_SIZE_CARD_CONTENT.replace('px', '')))
        self._font_metrics = QFontMetrics(self._font)

        self._init_ui()
        self._set_content_based_on_type()
        self.setStyleSheet(get_clipboard_card_style(self._is_pinned))

    @property
    def is_pinned(self):
        return self._is_pinned

    @is_pinned.setter
    def is_pinned(self, value):
        if self._is_pinned != value:
            self._is_pinned = value
            self.setStyleSheet(get_clipboard_card_style(self._is_pinned))

    def _get_font_metrics(self):
        return self._font_metrics

    def _create_content_label(self, text):
        label = QLabel(text, self)
        label.setFont(self._font)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setWordWrap(False)
        label.setFixedHeight(self._font_metrics.lineSpacing())
        return label

    def _truncate_text_by_width(self, text, max_width):
        if not text:
            return ""
        metrics = self._get_font_metrics()
        if metrics.horizontalAdvance(text) <= max_width:
            return text
        return metrics.elidedText(text, Qt.ElideRight, max_width)

    def _truncate_path_end_by_width(self, path, max_width):
        if not path: return ""
        metrics = self._get_font_metrics()
        if metrics.horizontalAdvance(path) <= max_width: return path
        
        ellipsis_text = "..."
        ellipsis_width = metrics.horizontalAdvance(ellipsis_text)
        if max_width <= ellipsis_width: return ellipsis_text
        
        remaining_width = max_width - ellipsis_width
        accumulated = []
        current_width = 0
        for char in reversed(path):
            char_width = metrics.horizontalAdvance(char)
            if current_width + char_width <= remaining_width:
                accumulated.append(char)
                current_width += char_width
            else:
                break
        return ellipsis_text + "".join(reversed(accumulated))

    def _clear_content_layout(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(
            CARD_INTERNAL_CONTENT_PADDING, CARD_INTERNAL_CONTENT_PADDING,
            CARD_INTERNAL_CONTENT_PADDING, CARD_INTERNAL_CONTENT_PADDING
        )
        main_layout.setSpacing(CARD_INTERNAL_SPACING)
        main_layout.addLayout(self.content_layout)
        main_layout.addStretch(1)

    def _set_content_based_on_type(self):
        self._clear_content_layout()
        available_width = CARD_WIDTH_FIXED - (CARD_INTERNAL_CONTENT_PADDING * 2)
        available_height = CARD_HEIGHT_FIXED - (CARD_INTERNAL_CONTENT_PADDING * 2)
        icon_width = 20
        spacing_after = 5
        
        try:
            if self.clip_type == "TEXT": 
                original_text = self.clip_content 
                if not original_text.strip(): 
                    self.content_layout.addWidget(self._create_content_label("(无内容)"))
                else:
                    max_lines = 3 
                    lines = original_text.split('\n')
                    for i, line in enumerate(lines):
                        if i >= max_lines: break 
                        truncated = self._truncate_text_by_width(line, available_width) 
                        self.content_layout.addWidget(self._create_content_label(truncated))
                    
            elif self.clip_type == "IMAGE":
                if not self.clip_content:
                    self.content_layout.addWidget(self._create_content_label("图像 (无数据)"))
                else:
                    image_data_b64 = None
                    try:
                        image_content = json.loads(self.clip_content)
                        if isinstance(image_content, dict) and "image_data" in image_content:
                            image_data_b64 = image_content["image_data"]
                        else:
                            image_data_b64 = self.clip_content
                    except json.JSONDecodeError:
                        image_data_b64 = self.clip_content

                    cached_pixmap = get_cached_scaled_image(image_data_b64, available_width, available_height)
                    
                    if cached_pixmap:
                        image_label = QLabel(self)
                        image_label.setPixmap(cached_pixmap)
                        image_label.setScaledContents(False)
                        image_label.setProperty("image", True)
                        image_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        self.content_layout.addWidget(image_label)
                    else:
                        placeholder = QLabel(self)
                        placeholder.setText("加载中...")
                        placeholder.setAlignment(Qt.AlignCenter)
                        self.content_layout.addWidget(placeholder)
                        self._async_load_image(placeholder, image_data_b64, available_width, available_height)

            elif self.clip_type == "FILES":
                try:
                    clip_data = json.loads(self.clip_content)
                    original_paths = clip_data.get("original_paths", [])
                except json.JSONDecodeError:
                    original_paths = [p for p in self.clip_content.split('\n') if p.strip()]

                if not original_paths:
                    self.content_layout.addWidget(self._create_content_label(f"{ICON_FILE} (无文件内容)"))
                else:
                    file_count = len(original_paths)
                    first_path = original_paths[0]
                    first_filename = os.path.basename(first_path)
                    first_folder = os.path.dirname(first_path)
                    available_text_width = available_width - icon_width - spacing_after - 10 
                    metrics = self._get_font_metrics()
                    
                    display_filename = self._truncate_text_by_width(first_filename, available_text_width - 50)
                    display_folder = self._truncate_path_end_by_width(first_folder, available_text_width)

                    if file_count == 1:
                        first_line = f"{ICON_FILE} {display_filename}"
                    else:
                        count_text = f" (+{file_count - 1} 个文件)"
                        combined = f"{display_filename}{count_text}"
                        if metrics.horizontalAdvance(f"{ICON_FILE} {combined}") > available_text_width:
                            remaining = available_text_width - metrics.horizontalAdvance(f"{ICON_FILE} {count_text}")
                            display_filename = self._truncate_text_by_width(first_filename, remaining - 10)
                            if not display_filename.endswith("..."): display_filename += "..."
                            first_line = f"{ICON_FILE} {display_filename}{count_text}" 
                        else:
                            first_line = f"{ICON_FILE} {combined}"

                    self.content_layout.addWidget(self._create_content_label(first_line))
                    self.content_layout.addWidget(self._create_content_label(display_folder))
            else:
                content_str = str(self.clip_content).strip() or "(未知类型，无内容)"
                display_text = f"未知类型: {content_str}"
                display_text = self._truncate_text_by_width(display_text, available_width - 20)
                self.content_layout.addWidget(self._create_content_label(display_text))

        except (TypeError, ValueError, AttributeError):
            self.content_layout.addWidget(self._create_content_label(f"错误: 无法显示内容 (ID: {self.clip_id})"))

    def _async_load_image(self, label, image_data_b64, width, height):
        class ImageLoader(QRunnable):
            def __init__(self, image_data_b64, width, height, label, card_instance):
                super().__init__()
                self.image_data_b64 = image_data_b64
                self.width = width
                self.height = height
                self.label = label
                self.card_instance = card_instance
                
            def run(self):
                try:
                    pixmap = get_cached_scaled_image(self.image_data_b64, self.width, self.height)
                    if pixmap:
                        QMetaObject.invokeMethod(
                            self.card_instance, '_update_image_label',
                            Qt.QueuedConnection, Q_ARG(object, self.label), Q_ARG(object, pixmap)
                        )
                except Exception as e:
                    print(f"Async image load error: {e}")
        
        loader = ImageLoader(image_data_b64, width, height, label, self)
        QThreadPool.globalInstance().start(loader)

    def _update_image_label(self, label, pixmap):
        if label and pixmap:
            label.setText("")
            label.setPixmap(pixmap)
            label.setScaledContents(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self.clip_id, self.clip_type, self.clip_content)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(get_context_menu_style())
        pin_text = "取消置顶" if self.is_pinned else "置顶"
        pin_action = QAction(pin_text, self)
        export_action = QAction("导出", self)
        delete_action = QAction("删除", self)

        pin_action.triggered.connect(lambda: self.card_pin_toggled.emit(self.clip_id))
        export_action.triggered.connect(lambda: self.card_export.emit(self.clip_id))
        delete_action.triggered.connect(lambda: self.card_delete.emit(self.clip_id))

        menu.addAction(pin_action)
        if self.clip_type in ["TEXT", "IMAGE"]:
            menu.addAction(export_action)
        menu.addAction(delete_action)
        menu.exec(event.globalPos())

class SettingsDialog(QDialog):
    settings_changed = Signal()
    
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setModal(True)
        self.setFixedSize(220, 160)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)  
        self._init_ui()
        self._load_settings_to_ui()
        self.setStyleSheet(get_settings_dialog_style())
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(15, 15, 15, 15)
        
        clean_layout = QHBoxLayout()
        clean_layout.setSpacing(10)
        self.auto_clean_checkbox = QCheckBox("自动清理")
        clean_layout.addWidget(self.auto_clean_checkbox)
        self.days_combo_box = QComboBox()
        self.days_combo_box.addItems(["1天", "5天", "10天", "15天", "30天"])
        self.days_combo_box.setFixedWidth(70)
        clean_layout.addWidget(self.days_combo_box)
        clean_layout.addStretch()
        
        history_layout = QHBoxLayout()
        history_layout.setSpacing(10)
        self.max_history_checkbox = QCheckBox("最大历史记录")
        history_layout.addWidget(self.max_history_checkbox)
        self.history_combo_box = QComboBox()
        self.history_combo_box.addItems(["50", "100", "200", "500", "1000", "2000"]) 
        self.history_combo_box.setFixedWidth(70)
        history_layout.addWidget(self.history_combo_box)
        history_layout.addStretch()
        
        self.paste_as_file_checkbox = QCheckBox("粘贴图像为文件")
        
        layout.addLayout(clean_layout)
        layout.addLayout(history_layout)        
        layout.addWidget(self.paste_as_file_checkbox)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.setContentsMargins(0, 10, 0, 0)
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.ok_button.setFixedHeight(28)
        self.cancel_button.setFixedHeight(28)
        self.ok_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cancel_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.ok_button.clicked.connect(self._accept_settings_and_emit)
        self.cancel_button.clicked.connect(self.reject)
    
    def _load_settings_to_ui(self):
        self.auto_clean_checkbox.setChecked(self.settings_manager.get("auto_clean_enabled", False))        
        days_value = self.settings_manager.get("auto_clean_days", 7)
        combo_index = self._get_combo_index_from_days(days_value)
        self.days_combo_box.setCurrentIndex(combo_index)
        self.max_history_checkbox.setChecked(self.settings_manager.get("max_history_enabled", True))
        max_history_count = self.settings_manager.get("max_history_count", 100)
        combo_items = [int(self.history_combo_box.itemText(i)) for i in range(self.history_combo_box.count())]
        try:
            index = combo_items.index(max_history_count)
            self.history_combo_box.setCurrentIndex(index)
        except ValueError:
            self.history_combo_box.setCurrentIndex(combo_items.index(100) if 100 in combo_items else 0)
        self.paste_as_file_checkbox.setChecked(self.settings_manager.get("paste_as_file_enabled", False))
        
    def _get_combo_index_from_days(self, days):
        if days <= 0.01: return 0
        days_options = [1, 5, 10, 15, 30]
        min_diff = abs(days - days_options[0])
        closest_index = 0
        for i, option_days in enumerate(days_options):
            diff = abs(days - option_days)
            if diff < min_diff:
                min_diff = diff
                closest_index = i
        return closest_index 
    
    def _get_days_from_combo_index(self, index):
        days_options = [1, 5, 10, 15, 30]
        return days_options[index] if 0 <= index < len(days_options) else 7
    
    def _accept_settings_and_emit(self):
        current_settings = {
            "auto_clean_enabled": self.auto_clean_checkbox.isChecked(),
            "auto_clean_days": self._get_days_from_combo_index(self.days_combo_box.currentIndex()),
            "max_history_enabled": self.max_history_checkbox.isChecked(),
            "max_history_count": int(self.history_combo_box.currentText()),
            "paste_as_file_enabled": self.paste_as_file_checkbox.isChecked(),
        }
        self.settings_manager.save_settings(current_settings)
        self.settings_changed.emit()
        self.accept()

    def showEvent(self, event):
        if self.parent():
            parent_center = self.parent().geometry().center()
            self.move(parent_center.x() - self.width() // 2, parent_center.y() - self.height() // 2)
        super().showEvent(event)

class MainWindowUI(QMainWindow):
    settings_requested = Signal()
    error_message_requested = Signal(str, str)
    info_message_requested = Signal(str, str)
    warning_message_requested = Signal(str, str)
    question_message_requested = Signal(str, str, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartClipboard")
        self.setFixedSize(WINDOW_WIDTH + BORDER_WIDTH * 2, WINDOW_HEIGHT + BORDER_WIDTH * 2)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._is_dragging = False
        self._drag_position = QPoint()

        self.container_widget = QWidget()
        self.setCentralWidget(self.container_widget)
        self.container_widget.setObjectName("container_widget")

        self.main_layout = QVBoxLayout(self.container_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_header()
        self.main_layout.addWidget(self.title_bar)

        # 设置搜索栏
        self._setup_search_bar()
        self.main_layout.addWidget(self.search_bar_container)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(
            PADDING_LEFT + BORDER_WIDTH,
            PADDING_TOP + BORDER_WIDTH,
            PADDING_RIGHT + BORDER_WIDTH,
            PADDING_BOTTOM + BORDER_WIDTH
        )
        content_layout.setSpacing(SPACING)

        self._setup_card_area()
        content_layout.addWidget(self.scroll_area)
        self.main_layout.addLayout(content_layout)

        self.setStyleSheet(get_main_window_style())
        if hasattr(self, 'title_bar'):
            self.title_bar.setStyleSheet(get_title_bar_style())

    def set_no_activate(self):
        if win32gui and win32con:
            hwnd = self.winId()
            if hwnd:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_NOACTIVATE)

    def _setup_header(self):
        self.title_bar = TitleBar()
        self.title_bar.settings_requested.connect(self.settings_requested.emit)
        self.title_bar.close_requested.connect(self.hide)

    def _setup_search_bar(self):
        """设置搜索框"""
        # 创建搜索框容器，用于居中显示
        self.search_bar_container = QWidget()
        self.search_bar_container.setObjectName("search_bar_container")
        search_bar_layout = QHBoxLayout(self.search_bar_container)
        search_bar_layout.setContentsMargins(0, 0, 0, 0)
        search_bar_layout.setSpacing(0)
        
        # 添加左侧弹性空间
        search_bar_layout.addStretch()
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("搜索")
        self.search_bar.setFixedHeight(28)
        self.search_bar.setFixedWidth(CARD_WIDTH_FIXED)
        self.search_bar.setStyleSheet(get_search_bar_style())
        self.search_bar.setObjectName("search_bar")
        search_bar_layout.addWidget(self.search_bar)
        
        # 添加右侧弹性空间
        search_bar_layout.addStretch()
        
        # 默认隐藏
        self.search_bar_container.hide()
        return self.search_bar_container

    def _setup_card_area(self):
            self.scroll_area = QScrollArea()
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

            # 使用 QListView 替代卡片容器
            self.list_view = QListView()
            self.list_view.setObjectName("list_view")

            # 关键设置1：确保按“项目”进行滚动，而不是按像素
            self.list_view.setVerticalScrollMode(QListView.ScrollPerItem)

            self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.list_view.setSpacing(SPACING)
            self.list_view.setCursor(Qt.PointingHandCursor)

            # ============================================================
            # 补丁：自定义滚轮事件，实现一次滚动 2 行
            # ============================================================
            def custom_wheel_event(event):
                # 获取垂直滚动条
                v_scrollbar = self.list_view.verticalScrollBar()

                # 获取滚轮滚动的角度 delta (通常 120 或 -120)
                delta = event.angleDelta().y()

                if delta == 0:
                    return

                # 定义一次滚动的行数
                scroll_step = 2

                # 当前滚动条的位置（在 ScrollPerItem 模式下，这就是行号）
                current_value = v_scrollbar.value()

                if delta > 0:
                    # 向上滚动 (滚轮向前)
                    new_value = max(0, current_value - scroll_step)
                else:
                    # 向下滚动 (滚轮向后)
                    new_value = min(v_scrollbar.maximum(), current_value +  scroll_step)

                # 应用新位置
                v_scrollbar.setValue(new_value)

                # 接受事件，防止父类处理（否则会产生双重滚动或默认滚动）
                event.accept()

            # 将自定义方法绑定到实例上 (Monkey Patching)
            self.list_view.wheelEvent = custom_wheel_event
            # ============================================================

            # 设置列表容器的样式
            self.list_view.setStyleSheet(f"""
                QListView {{
                    background-color: {COLOR_BACKGROUND};
                    border: none;
                    outline: none;
                }}
                QListView::item {{
                    background-color: transparent;
                    border: none;
                }}
                QListView::item:selected {{
                    background-color: {COLOR_BUTTON_HOVER};
                    border: none;
                }}
            """)

            self.scroll_area.setWidget(self.list_view)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self.move(event.globalPosition().toPoint() - self._drag_position)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        event.ignore()


# ============================================================
# Section: Main Application Logic
# ============================================================

class SmartClipboardApp(MainWindowUI):

    def __init__(self):
        super().__init__()

        self.current_dir = get_app_data_path()
        self.settings_manager = SettingsManager(self.current_dir)
        self.db_manager = DatabaseManager(self.current_dir)
        self.clipboard = QApplication.clipboard()
        self.normalized_app_root_dir = os.path.normpath(self.current_dir)
        
        self._last_system_clipboard_hash = None
        self._last_system_clipboard_data = None
        self._initialize_current_clipboard_state()

        self.clipboard.dataChanged.connect(self._on_clipboard_data_changed)

        logging.info("Clipboard monitoring switched to dataChanged signal.")

        self._ignore_next_clipboard_event = False
        self._is_settings_dialog_open = False

        # 初始化 Model 和 Delegate
        self.model = ClipboardModel(self)
        self.delegate = ClipboardDelegate(self)
        
        # 设置搜索过滤器
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterRole(ClipboardModel.RoleContentPreview)
        
        # 绑定到 View
        self.list_view.setModel(self.proxy_model)
        self.list_view.setItemDelegate(self.delegate)
        
        # 处理点击事件
        self.list_view.clicked.connect(self._on_list_item_clicked)
        
        # 处理右键菜单
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)

        self._setup_persistence_dirs()
        QApplication.instance().aboutToQuit.connect(self._cleanup_on_quit)

        self.settings_requested.connect(self._on_settings_requested)
        self.error_message_requested.connect(self._show_error_message_ui)
        self.info_message_requested.connect(self._show_info_message_ui)
        self.warning_message_requested.connect(self._show_warning_message_ui)
        self.question_message_requested.connect(self._show_question_message_ui_slot)

        # 连接搜索框信号
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        self.search_bar.returnPressed.connect(self._on_search_return_pressed)
        
        # 安装事件过滤器用于Ctrl+F快捷键
        # 安装到主窗口以确保在窗口激活时也能捕获Ctrl+F
        self.list_view.installEventFilter(self)
        self.search_bar.installEventFilter(self)
        self.installEventFilter(self)

        self.setup_tray_icon()
        self.load_clips_from_db()

        self.paste_timer = QTimer(self)
        self.paste_timer.setSingleShot(True)
        self.paste_timer.timeout.connect(self._perform_paste_hotkey)

        self.keyboard_controller = Controller()

        self.hotkey_listener = WinHotkeyListener(self)
        self.hotkey_listener.hotkeyPressed.connect(self.show_and_position_window_on_hotkey)
        self.hotkey_listener.start_listening()
        self._perform_startup_clean()

        self.hide()
        self.set_no_activate()
        
        # === 新增代码开始：处理 Enter 键粘贴 ===
        # 保存原始的按键事件处理函数
        self._original_list_key_press = self.list_view.keyPressEvent

        def custom_list_key_press(event):
            # 如果按下的是回车键 (大键盘 Enter 或小键盘 Enter)
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                index = self.list_view.currentIndex()
                if index.isValid():
                    # 调用点击处理逻辑 (即粘贴逻辑)
                    self._on_list_item_clicked(index)
                event.accept()
            else:
                # 其他按键 (如上下键) 交给原生方法处理
                self._original_list_key_press(event)

        # 替换 list_view 的按键事件处理
        self.list_view.keyPressEvent = custom_list_key_press
        # === 新增代码结束 ===

    def eventFilter(self, obj, event):
        """事件过滤器，处理Ctrl+F快捷键和搜索框的Escape键"""
        if event.type() == QEvent.Type.KeyPress:
            key_event = QKeyEvent(event)
            if key_event.key() == Qt.Key_F and (key_event.modifiers() & Qt.ControlModifier):
                self._toggle_search_bar()
                return True
            # 处理搜索框的Escape键
            if obj == self.search_bar and key_event.key() == Qt.Key_Escape:
                self._on_search_escape()
                return True
        return super().eventFilter(obj, event)

    def _toggle_search_bar(self):
        """切换搜索框的显示/隐藏"""
        if self.search_bar_container.isVisible():
            self.search_bar_container.hide()
            self.search_bar.clear()
            self.proxy_model.setFilterFixedString("")
        else:
            self.search_bar_container.show()
            self.search_bar.setFocus()
            self.search_bar.selectAll()

    def _on_search_text_changed(self, text):
        """搜索文本变化时的处理"""
        self.proxy_model.setFilterFixedString(text)
        # 如果有搜索结果，选中第一项
        if self.proxy_model.rowCount() > 0:
            first_index = self.proxy_model.index(0, 0)
            if first_index.isValid():
                self.list_view.setCurrentIndex(first_index)
                self.list_view.selectionModel().select(
                    first_index,
                    QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
                )

    def _on_search_return_pressed(self):
        """搜索框按回车键时粘贴选中的项"""
        current_index = self.list_view.currentIndex()
        if current_index.isValid():
            # 将代理模型的索引转换为源模型的索引
            source_index = self.proxy_model.mapToSource(current_index)
            if source_index.isValid():
                self._on_list_item_clicked(source_index)

    def _clear_search_state(self):
        """清除搜索框状态：隐藏搜索框、清除搜索文本、重置过滤"""
        self.search_bar_container.hide()
        self.search_bar.clear()
        self.proxy_model.setFilterFixedString("")
        self.list_view.setFocus()

    def _on_search_escape(self):
        """搜索框按Escape键时隐藏搜索框"""
        self._clear_search_state()

    def _setup_persistence_dirs(self):
        temp_dir_path = os.path.join(self.current_dir, TEMP_DIR_NAME)
        try:
            os.makedirs(temp_dir_path, exist_ok=True)
            logging.info(f"Ensured temp directory exists: {temp_dir_path}")
        except (OSError, IOError) as e:
            logging.error(f"Failed to create temp directory {temp_dir_path}: {e}")

    def _cleanup_on_quit(self):
        temp_dir_path = os.path.join(self.current_dir, TEMP_DIR_NAME)
        if os.path.exists(temp_dir_path):
            try:
                shutil.rmtree(temp_dir_path)
                logging.info(f"Cleaned up temp directory on quit: {temp_dir_path}")
            except (shutil.Error, OSError, IOError) as e:
                logging.warning(f"Failed to clean up temp directory {temp_dir_path} on quit: {e}")
        if self.db_manager:
            try:
                self.db_manager.close()
                logging.info("Database connection closed on quit.")
            except Exception as e:
                logging.warning(f"Error closing database connection on quit: {e}")

    def _perform_startup_clean(self):
        if self.settings_manager.get("auto_clean_enabled", False):
            days = self.settings_manager.get("auto_clean_days", 7)
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            cutoff_date_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')
            ids_to_delete = []
            self.db_manager.cursor.execute(
                "SELECT id, type, content FROM clips WHERE timestamp < ? AND is_pinned = FALSE",
                (cutoff_date_str,)
            )
            expired_records = self.db_manager.cursor.fetchall()
            for record_id, _, _ in expired_records:
                ids_to_delete.append(record_id)

            deleted_count = 0
            for clip_id in ids_to_delete:
                if self.db_manager.delete_clip(clip_id):
                    deleted_count += 1
            
            if deleted_count > 0:
                self.load_clips_from_db()
                logging.info(f"Startup clean completed: Deleted {deleted_count} expired records.")

    def _calculate_hash(self, clip_type, content):
        content_str = str(content) if content is not None else ""
        return hashlib.md5(f"{clip_type}:{content_str}".encode('utf-8')).hexdigest()

    def _initialize_current_clipboard_state(self):
        logging.info("Initializing internal clipboard state with current system clipboard content.")
        mime_data = self.clipboard.mimeData()
        try:
            current_extracted_data = self._extract_clipboard_data(mime_data)
            if current_extracted_data is not None:
                clip_type, serialized_content = current_extracted_data
                self._last_system_clipboard_hash = self._get_content_hash(clip_type, serialized_content)
                self._last_system_clipboard_data = current_extracted_data
                logging.debug(f"Initial clipboard state set. Hash: {self._last_system_clipboard_hash}")
            else:
                self._last_system_clipboard_hash = None
                self._last_system_clipboard_data = None
                logging.debug("Initial clipboard state set to empty/unrecognized.")
        except Exception as e:
            logging.error(f"Error during initial clipboard state setup: {e}")
            self._last_system_clipboard_hash = None
            self._last_system_clipboard_data = None

    def _on_clipboard_data_changed(self):
        logging.debug(f"[_on_clipboard_data_changed] Clipboard data changed signal received.")

        if self._ignore_next_clipboard_event:
            self._ignore_next_clipboard_event = False
            logging.debug("[_on_clipboard_data_changed] Ignoring next clipboard event (due to internal paste).")
            return

        mime_data = self.clipboard.mimeData()
        current_extracted_data = None
        try:
            current_extracted_data = self._extract_clipboard_data(mime_data)
        except Exception as e:
            logging.error(f"[_on_clipboard_data_changed] Error extracting clipboard data: {e}")
            return

        if current_extracted_data is None:
            if self._last_system_clipboard_hash is not None:
                self._last_system_clipboard_hash = None
                self._last_system_clipboard_data = None
            return

        clip_type, serialized_content = current_extracted_data
        current_composite_hash = self._get_content_hash(clip_type, serialized_content)

        if current_composite_hash == self._last_system_clipboard_hash:
            self._last_system_clipboard_data = current_extracted_data
            return
        
        logging.info(f"[_on_clipboard_data_changed] Hashes differ, processing new content. Type: {clip_type}")
        self._last_system_clipboard_hash = current_composite_hash
        self._last_system_clipboard_data = current_extracted_data
        self._process_new_system_clipboard_content(clip_type, serialized_content)

    def _get_content_hash(self, clip_type, serialized_content):
        if clip_type == "FILES":
            try:
                content_obj = json.loads(serialized_content)
                return content_obj.get("metadata_hash")
            except json.JSONDecodeError:
                return hashlib.md5(serialized_content.encode('utf-8')).hexdigest()
        else:
            return self._calculate_hash(clip_type, serialized_content)

    def _process_new_system_clipboard_content(self, clip_type, serialized_content):
        # 处理去重逻辑 - 检查 Model 中是否有相同内容
        duplicate_clip_id = None
        current_clip_hash = self._get_content_hash(clip_type, serialized_content)
        
        # 遍历 Model 检查重复
        for i, clip in enumerate(self.model._clips):
            clip_id, clip_type_in_model, clip_content_in_model, is_pinned = clip
            if not is_pinned:
                card_clip_hash = self._get_content_hash(clip_type_in_model, clip_content_in_model)
                if card_clip_hash == current_clip_hash:
                    duplicate_clip_id = clip_id
                    break
        
        # 删除重复项
        if duplicate_clip_id is not None:
            self.db_manager.delete_clip(duplicate_clip_id)
            self.model.remove_row_by_id(duplicate_clip_id)

        if clip_type == "FILES":
            try:
                clip_data = json.loads(serialized_content)
                clip_data["copied_paths"] = [] 
                serialized_content = json.dumps(clip_data, ensure_ascii=False, sort_keys=True)
            except Exception as e:
                self.show_error_message("文件处理错误", f"处理文件剪贴板内容时发生错误: {e}")
                return

        new_id = self.db_manager.add_clip(clip_type, serialized_content, is_pinned=False)
        if new_id is None:
            self.show_error_message("保存剪贴板内容失败", "无法将新的剪贴板内容保存到数据库。")
            return

        if self.settings_manager.get("max_history_enabled", False):
            max_count = int(self.settings_manager.get("max_history_count", 100))
            deleted_ids = self.db_manager.enforce_max_history(max_count)
            if deleted_ids:
                for deleted_clip_id in deleted_ids:
                    self.model.remove_row_by_id(deleted_clip_id)

        # 重新加载数据
        self.load_clips_from_db()

        if self.isVisible():
            self.update()
            QApplication.processEvents()

    def _normalize_text(self, text):
        if not text: return ""
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.rstrip() 
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    def _extract_clipboard_data(self, mime_data):
        available_formats = list(mime_data.formats())

        if mime_data.hasImage():
            image = mime_data.imageData()
            if isinstance(image, QImage) and not image.isNull():
                byte_array = QByteArray()
                buffer = QBuffer(byte_array)
                buffer.open(QBuffer.WriteOnly)
                if image.save(buffer, "PNG"):
                    serialized_content = base64.b64encode(byte_array.data()).decode('utf-8')
                    return ("IMAGE", serialized_content)

        image_mime_types = ["image/png", "image/jpeg", "image/bmp", "image/gif", "image/tiff"]
        for mime_type in image_mime_types:
            if mime_type in available_formats:
                image_data_from_format = mime_data.data(mime_type)
                if not image_data_from_format.isEmpty():
                    image = QImage()
                    if image.loadFromData(image_data_from_format):
                        byte_array = QByteArray()
                        buffer = QBuffer(byte_array)
                        buffer.open(QBuffer.WriteOnly)
                        if image.save(buffer, "PNG"):
                            serialized_content = base64.b64encode(byte_array.data()).decode('utf-8')
                            return ("IMAGE", serialized_content)

        if mime_data.hasUrls():
            urls = mime_data.urls()
            present_local_file_paths = []

            for url in urls:
                if url.isLocalFile():
                    local_path = os.path.normpath(url.toLocalFile())
                    if os.path.exists(local_path):
                        present_local_file_paths.append(local_path)

            is_self_copy = False
            if present_local_file_paths:
                ignore_dirs = [
                    self.normalized_app_root_dir,
                    os.path.normpath(os.path.join(self.current_dir, TEMP_DIR_NAME))
                ]
                for p in present_local_file_paths:
                    for ignore in ignore_dirs:
                        if p == ignore or os.path.commonpath([p, ignore]) == ignore:
                            is_self_copy = True
                            break
                    if is_self_copy: break

            if is_self_copy:
                return None

            if present_local_file_paths:
                image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp'}
                all_images = True
                for path in present_local_file_paths:
                    _, ext = os.path.splitext(path.lower())
                    if ext not in image_extensions:
                        all_images = False
                        break
                
                if all_images and len(present_local_file_paths) == 1:
                    image_path = present_local_file_paths[0]
                    image = QImage(image_path)
                    if not image.isNull():
                        byte_array = QByteArray()
                        buffer = QBuffer(byte_array)
                        buffer.open(QBuffer.WriteOnly)
                        if image.save(buffer, "PNG"):
                            serialized_content = base64.b64encode(byte_array.data()).decode('utf-8')
                            original_filename = os.path.basename(image_path)
                            image_with_metadata = {
                                "image_data": serialized_content,
                                "original_filename": original_filename
                            }
                            return ("IMAGE", json.dumps(image_with_metadata, ensure_ascii=False))

                file_paths_to_process = sorted(present_local_file_paths)
                metadata_hashes = []
                for p in file_paths_to_process:
                    metadata_hashes.append(get_file_metadata_hash(p))

                combined_metadata_hash = hashlib.md5("".join(sorted(metadata_hashes)).encode('utf-8')).hexdigest()
                clip_data = {
                    "original_paths": file_paths_to_process,
                    "copied_paths": [],
                    "metadata_hash": combined_metadata_hash
                }
                return ("FILES", json.dumps(clip_data, ensure_ascii=False, sort_keys=True))

        plain_text = mime_data.text() if mime_data.hasText() else ""
        html_text = mime_data.html() if mime_data.hasHtml() else ""

        if html_text:
            try:
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = False
                h.body_width = 0
                converted_text = h.handle(html_text)
                if converted_text:
                    return ("TEXT", self._normalize_text(converted_text))
            except Exception:
                pass
        
        if plain_text:
            return ("TEXT", self._normalize_text(plain_text))

        return None

    def load_clips_from_db(self):
        """
        重写：不再手动创建 Card，而是查询数据给 Model
        """
        # Pre-process: convert single image files to IMAGE type if needed
        clips = self.db_manager.get_all_clips()
        for clip_id, clip_type, clip_content, is_pinned in clips:
            if clip_type == "FILES":
                try:
                    clip_data = json.loads(clip_content)
                    original_paths = clip_data.get("original_paths", [])
                    if len(original_paths) == 1:
                        path = original_paths[0]
                        _, ext = os.path.splitext(path.lower())
                        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp'}
                        
                        if ext in image_extensions and os.path.exists(path):
                            image = QImage(path)
                            if not image.isNull():
                                byte_array = QByteArray()
                                buffer = QBuffer(byte_array)
                                buffer.open(QBuffer.WriteOnly)
                                if image.save(buffer, "PNG"):
                                    serialized = base64.b64encode(byte_array.data()).decode('utf-8')
                                    meta = {
                                        "image_data": serialized,
                                        "original_filename": os.path.basename(path)
                                    }
                                    new_content = json.dumps(meta, ensure_ascii=False)
                                    self.db_manager.update_clip_content(clip_id, new_content)
                                    self.db_manager.update_clip_type(clip_id, "IMAGE")
                except Exception:
                    pass

        # 获取数据并刷新 Model
        clips = self.db_manager.get_all_clips()
        self.model.set_data_list(clips)
        
        # 滚动到顶部
        if self.list_view.verticalScrollBar():
            self.list_view.verticalScrollBar().setValue(0)
        
        # 如果有搜索文本，重新应用过滤
        if self.search_bar_container.isVisible() and self.search_bar.text():
            self.proxy_model.setFilterFixedString(self.search_bar.text())
            # 选中第一项
            if self.proxy_model.rowCount() > 0:
                first_index = self.proxy_model.index(0, 0)
                if first_index.isValid():
                    self.list_view.setCurrentIndex(first_index)

    def _on_list_item_clicked(self, index):
        """替代原来的 _on_card_clicked - 处理列表项点击"""
        if not index.isValid():
            return
        
        # 如果是代理模型的索引，转换为源模型索引
        if isinstance(index.model(), QSortFilterProxyModel):
            index = self.proxy_model.mapToSource(index)
            if not index.isValid():
                return
        
        clip_id = index.data(ClipboardModel.RoleId)
        clip_type = index.data(ClipboardModel.RoleType)
        content = index.data(ClipboardModel.RoleContent)
        
        # 复用原有的粘贴逻辑
        self._perform_paste_logic(clip_id, clip_type, content)
    
    def _perform_paste_logic(self, clip_id, clip_type, content):
        """执行粘贴逻辑 - 提取自原来的 _on_card_clicked"""
        self._ignore_next_clipboard_event = True
        mime_data = QMimeData()
        paste_successful = False

        try:
            if clip_type == "TEXT":
                mime_data.setText(content)
                paste_successful = True
            elif clip_type == "IMAGE":
                original_filename = None
                image_data_b64 = content
                try:
                    image_content = json.loads(content)
                    if isinstance(image_content, dict) and "image_data" in image_content:
                        image_data_b64 = image_content["image_data"]
                        original_filename = image_content.get("original_filename")
                except json.JSONDecodeError:
                    pass

                image = QImage()
                if image.loadFromData(QByteArray.fromBase64(image_data_b64.encode('utf-8'))):
                    if self.settings_manager.get("paste_as_file_enabled", False):
                        temp_dir = os.path.join(self.current_dir, TEMP_DIR_NAME)
                        os.makedirs(temp_dir, exist_ok=True)
                        if original_filename:
                            temp_file = os.path.join(temp_dir, original_filename)
                        else:
                            ts = datetime.datetime.now().strftime("%Y-%m-%d %H%M%S")
                            temp_file = os.path.join(temp_dir, f"ClipboardImage {ts}.png")
                        
                        if image.save(temp_file, "PNG"):
                            mime_data.setUrls([QUrl.fromLocalFile(temp_file)])
                            paste_successful = True
                        else:
                            mime_data.setImageData(image)
                            paste_successful = True
                    else:
                        mime_data.setImageData(image)
                        paste_successful = True
            elif clip_type == "FILES":
                try:
                    clip_data = json.loads(content)
                    original_paths = clip_data.get("original_paths", [])
                    valid_urls = [QUrl.fromLocalFile(p) for p in original_paths if os.path.exists(os.path.normpath(p))]
                    if valid_urls:
                        mime_data.setUrls(valid_urls)
                        paste_successful = True
                    else:
                        self.show_error_message("文件无效", f"文件内容已丢失或路径无效 (ID: {clip_id})")
                        self._ignore_next_clipboard_event = False
                        return
                except Exception:
                    self._ignore_next_clipboard_event = False
                    return
            else:
                self._ignore_next_clipboard_event = False
                return

            if paste_successful:
                self.clipboard.setMimeData(mime_data)
                
                # Update internal state to avoid self-trigger loop
                try:
                    state = self._extract_clipboard_data(self.clipboard.mimeData())
                    if state:
                        self._last_system_clipboard_hash = self._get_content_hash(state[0], state[1])
                        self._last_system_clipboard_data = state
                except Exception:
                    pass

                self.db_manager.update_clip_timestamp(clip_id)
                self.load_clips_from_db()
                self._clear_search_state()  # 粘贴后清除搜索状态
                self.hide()
                self.paste_timer.start(50)
            else:
                self._ignore_next_clipboard_event = False

        except Exception as e:
            self.show_error_message("粘贴失败", f"错误: {e}")
            self._ignore_next_clipboard_event = False

    def _perform_paste_hotkey(self):
        try:
            from pynput.keyboard import Key
            self.keyboard_controller.press(Key.ctrl_l)
            self.keyboard_controller.press('v')
            self.keyboard_controller.release('v')
            self.keyboard_controller.release(Key.ctrl_l)
        except Exception as e:
            logging.error(f"Failed to perform paste hotkey: {e}")

    def _on_context_menu(self, pos):
        """替代原来的 contextMenuEvent - 处理右键菜单"""
        index = self.list_view.indexAt(pos)
        if not index.isValid():
            return

        clip_id = index.data(ClipboardModel.RoleId)
        is_pinned = index.data(ClipboardModel.RoleIsPinned)
        clip_type = index.data(ClipboardModel.RoleType)
        
        menu = QMenu(self)
        menu.setStyleSheet(get_context_menu_style())
        
        pin_text = "取消置顶" if is_pinned else "置顶"
        action_pin = menu.addAction(pin_text)
        action_export = menu.addAction("导出")
        action_delete = menu.addAction("删除")
        
        action = menu.exec(self.list_view.mapToGlobal(pos))
        
        if action == action_pin:
            self._on_card_pin_toggled(clip_id, is_pinned)
        elif action == action_export:
            self._on_card_export(clip_id)
        elif action == action_delete:
            self._on_card_delete(clip_id)
    
    def _on_card_delete(self, clip_id):
        """根据 ID 删除剪贴板项"""
        reply = self.show_question_message("确认删除", "确定要删除该剪贴板内容吗？")
        if reply == QMessageBox.Yes:
            if self.db_manager.delete_clip(clip_id):
                # 直接操作 Model 删除，不需要重新加载 DB
                self.model.remove_row_by_id(clip_id)

    def _on_card_pin_toggled(self, clip_id, current_pin_status):
        """切换置顶状态"""
        new_status = not current_pin_status
        if self.db_manager.toggle_pin_status(clip_id, new_status):
            # 重新加载整个列表以触发布局排序变化
            self.load_clips_from_db()

    def _on_card_export(self, clip_id):
        """根据 ID 导出剪贴板内容"""
        clip = self.model.get_clip_by_id(clip_id)
        if not clip:
            return
        
        clip_id, clip_type, content, is_pinned = clip

        if clip_type == "TEXT":
            file_path, _ = QFileDialog.getSaveFileName(self, "导出文本", "clipboard_export.txt", "Text Files (*.txt);;All Files (*)")
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f: f.write(content)
                    self.show_info_message("导出成功", f"文本已导出到: {file_path}")
                except Exception as e:
                    self.show_error_message("导出失败", str(e))
        elif clip_type == "IMAGE":
            original_filename = None
            image_data_b64 = content
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    image_data_b64 = data.get("image_data", content)
                    original_filename = data.get("original_filename")
            except: pass

            default_name = original_filename or f"ClipboardImage {datetime.datetime.now().strftime('%Y-%m-%d %H%M%S')}.png"
            file_path, _ = QFileDialog.getSaveFileName(self, "导出图像", default_name, "PNG Files (*.png);;All Files (*)")
            if file_path:
                try:
                    img = QImage()
                    if img.loadFromData(QByteArray.fromBase64(image_data_b64.encode('utf-8'))):
                        img.save(file_path, "PNG")
                        self.show_info_message("导出成功", f"图像已导出到: {file_path}")
                    else:
                        raise Exception("图像数据无效")
                except Exception as e:
                    self.show_error_message("导出失败", str(e))
        elif clip_type == "FILES":
            try:
                data = json.loads(content)
                paths = data.get("original_paths", [])
                if not paths: return
                
                if len(paths) == 1 and os.path.isfile(paths[0]):
                    src = paths[0]
                    file_path, _ = QFileDialog.getSaveFileName(self, "导出文件", os.path.basename(src), "All Files (*)")
                    if file_path:
                        shutil.copy2(src, file_path)
                        self.show_info_message("导出成功", f"文件导出到: {file_path}")
                else:
                    target_dir = QFileDialog.getExistingDirectory(self, "选择导出目录")
                    if target_dir:
                        for p in paths:
                            if os.path.exists(p):
                                dest = os.path.join(target_dir, os.path.basename(p))
                                if os.path.isdir(p): shutil.copytree(p, dest, dirs_exist_ok=True)
                                else: shutil.copy2(p, dest)
                        self.show_info_message("导出成功", f"文件导出到: {target_dir}")
            except Exception as e:
                self.show_error_message("导出失败", str(e))

    def _show_error_message_ui(self, title, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setStyleSheet(get_message_box_style())
        msg_box.exec()

    def _show_info_message_ui(self, title, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setStyleSheet(get_message_box_style())
        msg_box.exec()

    def _show_warning_message_ui(self, title, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setStyleSheet(get_message_box_style())
        msg_box.exec()

    def _show_question_message_ui_slot(self, title, message, default_button):
        return self.show_question_message(title, message, default_button)

    def show_error_message(self, title, message):
        self.error_message_requested.emit(title, message)

    def show_info_message(self, title, message):
        self.info_message_requested.emit(title, message)

    def show_warning_message(self, title, message):
        self.warning_message_requested.emit(title, message)

    def show_question_message(self, title, message, default_button=QMessageBox.No):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(default_button)
        msg_box.setStyleSheet(get_message_box_style())
        return msg_box.exec()

    def _on_settings_requested(self):
        dialog = SettingsDialog(self.settings_manager, self)
        dialog.settings_changed.connect(self.on_settings_changed)
        self._is_settings_dialog_open = True
        dialog.exec()
        self._is_settings_dialog_open = False
        self.show()
        self.raise_()
        self.activateWindow()
        self.scroll_area.setFocus()

    def on_settings_changed(self):
        new_width = self.settings_manager.get("window_width", 300)
        new_height = self.settings_manager.get("window_height", 390)
        self.setFixedSize(new_width + BORDER_WIDTH * 2, new_height + BORDER_WIDTH * 2)

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        try:
            icon_path = resource_path("icon.png")
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                self.tray_icon.setIcon(QApplication.style().standardIcon(QStyle.SP_MessageBoxInformation))
        except Exception:
            self.tray_icon.setIcon(QApplication.style().standardIcon(QStyle.SP_MessageBoxInformation))

        self.tray_icon.setVisible(True)
        tray_menu = QMenu(self)
        tray_menu.setStyleSheet(get_tray_menu_style())
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)

    def _on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self.show_and_position_window_on_hotkey(from_tray=True, force_center=True)

    def quit_application(self):
        if self.paste_timer.isActive(): self.paste_timer.stop()
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()
            self.tray_icon = None
        if self.hotkey_listener:
            self.hotkey_listener.stop_listening()
        QApplication.quit()

    def _force_release_win_key(self):
        """双重保险：检测如果 Win 键逻辑上卡住，强制发送弹起信号"""
        try:
            # 检查 Win 键 (LWIN=0x5B, RWIN=0x5C) 是否被系统认为处于按下状态
            if (ctypes.windll.user32.GetAsyncKeyState(0x5B) & 0x8000) or \
               (ctypes.windll.user32.GetAsyncKeyState(0x5C) & 0x8000):
                
                # 定义结构体（如果前面没有全局定义，这里局部定义即可）
                class KEYBDINPUT(ctypes.Structure):
                    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                                ("dwExtraInfo", ctypes.c_void_p)]
                class INPUT(ctypes.Structure):
                    class _INPUT(ctypes.Union): _fields_ = [("ki", KEYBDINPUT)]
                    _anonymous_ = ("_input",)
                    _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]
                
                # 发送 Win Up
                inputs = (INPUT * 1)()
                inputs[0].type = 1
                inputs[0].ki.wVk = 0x5B # LWIN
                inputs[0].ki.dwFlags = 2 # KEYUP
                ctypes.windll.user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
                logging.info("Detected stuck Win key, forced release.")
        except Exception:
            pass

    def show_and_position_window_on_hotkey(self, from_tray=False, force_center=False):
        # 1. 先执行保险措施，防止按键状态错乱
        if not from_tray:
            self._force_release_win_key()
        
        # 隐藏窗口时清除搜索状态
        if self.isVisible():
            self._clear_search_state()
        
        if self._is_settings_dialog_open: return

        if self.isVisible():
            self.hide()
        else:
            self.load_clips_from_db()
            screen = QApplication.primaryScreen()
            if not screen: screen = QApplication.screenAt(QCursor.pos())

            x, y = 0, 0
            if screen:
                screen_geometry = screen.geometry()
                if force_center:
                    x = screen_geometry.center().x() - self.width() // 2
                    y = screen_geometry.center().y() - self.height() // 2
                elif not from_tray:
                    cursor_pos = QCursor.pos()
                    x = cursor_pos.x()
                    y = cursor_pos.y() - self.height() // 2
                    if x + self.width() > screen_geometry.right():
                        x = screen_geometry.right() - self.width()
                    if x < screen_geometry.left():
                        x = screen_geometry.left()
                    if y < screen_geometry.top():
                        y = screen_geometry.top()
                    if y + self.height() > screen_geometry.bottom():
                        y = screen_geometry.bottom() - self.height()
                else:
                    x = screen_geometry.center().x() - self.width() // 2
                    y = (QApplication.primaryScreen().size().height() - self.height()) // 2

            self.move(x, y)
            self.show()
            self.raise_()
            self.activateWindow() # 确保窗口处于激活状态以接收键盘输入
            
            # === 新增代码开始：自动选中第一项 ===
            self.list_view.setFocus() # 将键盘焦点给到列表
            
            if self.proxy_model.rowCount() > 0:
                # 获取第一项的索引
                first_index = self.proxy_model.index(0, 0)
                if first_index.isValid():
                    # 设置当前索引 (用于键盘导航的起点)
                    self.list_view.setCurrentIndex(first_index)
                    # 强制选中 (高亮显示)
                    self.list_view.selectionModel().select(
                        first_index, 
                        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
                    )
            # === 新增代码结束 ===
            
            # 这里的 setFocus 已经在上面处理了，可以移除原来的 self.scroll_area.setFocus()
            # self.scroll_area.setFocus() 


# ============================================================
# Section: Main Entry
# ============================================================

def main():
    # 检查自启动配置
    config_manager = AutoConfigManager()
    config_manager.setup_auto_start()
    
    app = QApplication(sys.argv)
    app.setApplicationName("SmartClipboard")
    
    # 防止多实例 (简单的检查)
    # 在生产环境中建议使用 QSharedMemory 或 Windows Mutex
    
    window = SmartClipboardApp()
    exit_code = app.exec()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()