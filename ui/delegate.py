"""
Clipboard item delegate for custom list rendering
"""
import json
import os

from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics
from PySide6.QtCore import Qt, QSize

from constants import (
    COLOR_CARD_BG, COLOR_TEXT_PRIMARY, COLOR_BUTTON_HOVER, COLOR_PINNED_BORDER,
    BORDER_WIDTH, CARD_WIDTH_FIXED, CARD_HEIGHT_FIXED, FONT_SIZE_CARD_CONTENT,
    FONT_FAMILY_ENGLISH, CARD_INTERNAL_CONTENT_PADDING, ICON_FILE
)
from core.image_cache import get_cached_scaled_image
from models import ClipboardModel


# 鼠标悬浮时的轻微高亮颜色（比选中更淡）
COLOR_HOVER_LIGHT = "#3a3a3a"


class ClipboardDelegate(QStyledItemDelegate):
    """Clipboard item delegate (Qt Delegate) - custom list item rendering"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = QFont(FONT_FAMILY_ENGLISH)
        self._font.setPixelSize(int(FONT_SIZE_CARD_CONTENT.replace('px', '')))

    def paint(self, painter, option, index):
        # Enable antialiasing for smooth rounded corners
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw background
        is_pinned = index.data(ClipboardModel.RoleIsPinned)

        # Set background color - 区分选中（方向键/点击）和悬浮（鼠标悬停）
        bg_color = QColor(COLOR_CARD_BG)
        if option.state & QStyle.State_Selected:
            # 选中状态 - 使用明显的高亮色
            bg_color = QColor(COLOR_BUTTON_HOVER)
        elif option.state & QStyle.State_MouseOver:
            # 悬浮状态 - 使用轻微高亮，与选中区分开
            bg_color = QColor(COLOR_HOVER_LIGHT)

        # Draw rounded rectangle background
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(option.rect, 4, 4)

        # Draw border (for pinned items)
        if is_pinned:
            pen = QPen(QColor(COLOR_PINNED_BORDER))
            pen.setWidth(BORDER_WIDTH)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(option.rect.adjusted(0, 0, -BORDER_WIDTH, -BORDER_WIDTH), 4, 4)

        # Get data
        clip_type = index.data(ClipboardModel.RoleType)
        content = index.data(ClipboardModel.RoleContent)

        # Draw content
        self._draw_content(painter, option, clip_type, content)

    def _draw_content(self, painter, option, clip_type, content):
        """Draw content based on type"""
        # Calculate content drawing area
        x = option.rect.left() + CARD_INTERNAL_CONTENT_PADDING
        y = option.rect.top() + CARD_INTERNAL_CONTENT_PADDING

        # Subtract padding
        available_width = option.rect.width() - (CARD_INTERNAL_CONTENT_PADDING * 2)
        available_height = option.rect.height() - (CARD_INTERNAL_CONTENT_PADDING * 2)

        try:
            if clip_type == "TEXT":
                self._draw_text(painter, x, y, available_width, available_height, content)
            elif clip_type == "IMAGE":
                self._draw_image(painter, x, y, available_width, available_height, content)
            elif clip_type == "FILES":
                self._draw_files(painter, x, y, available_width, available_height, content)
            else:
                self._draw_text(painter, x, y, available_width, available_height, str(content)[:50])
        except Exception as e:
            self._draw_text(painter, x, y, available_width, available_height, "[渲染错误]")

    def _draw_text(self, painter, x, y, max_width, max_height, text):
        """Draw text content (vertically centered)"""
        painter.setFont(self._font)
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))

        if not text.strip():
            text = "(无内容)"

        metrics = QFontMetrics(self._font)
        lines = text.split('\n')
        line_height = metrics.lineSpacing()

        # 1. Determine number of lines (max 3)
        max_lines = 3
        display_lines = lines[:max_lines]

        # 2. Calculate total text height
        total_text_height = len(display_lines) * line_height

        # 3. Calculate vertical centering offset
        y_offset = (max_height - total_text_height) // 2
        y_offset = max(0, y_offset)

        current_y = y + y_offset

        # 4. Draw lines
        for i, line in enumerate(display_lines):
            if (i + 1) * line_height > max_height:
                break

            elided = metrics.elidedText(line, Qt.ElideRight, max_width)
            baseline_y = current_y + (i + 1) * line_height - metrics.descent()
            painter.drawText(x, int(baseline_y), elided)

    def _draw_image(self, painter, x, y, max_width, max_height, content):
        """Draw image thumbnail (horizontally + vertically centered)"""
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
                # Keep aspect ratio scaling
                pixmap = cached_pixmap.scaled(
                    max_width, max_height,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )

                # Calculate center coordinates
                draw_x = x
                draw_y = y + (max_height - pixmap.height()) // 2

                painter.drawPixmap(draw_x, draw_y, pixmap)
            else:
                # Loading or failed text
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
        """Draw file list (vertically centered)"""
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

            # 1. Prepare text content
            first_path = original_paths[0]
            first_filename = os.path.basename(first_path)
            first_folder = os.path.dirname(first_path)
            file_count = len(original_paths)

            if file_count == 1:
                first_line = f"{ICON_FILE} {first_filename}"
            else:
                count_text = f" (+{file_count - 1} 个文件)"
                first_line = f"{ICON_FILE} {first_filename}{count_text}"

            # 2. Calculate total height of two lines
            total_height = line_height * 2

            # 3. Calculate vertical centering offset
            y_offset = (max_height - total_height) // 2
            y_offset = max(0, y_offset)
            current_y = y + y_offset

            # 4. Draw first line (filename)
            elided_filename = metrics.elidedText(first_line, Qt.ElideRight, max_width)
            baseline_1 = current_y + line_height - metrics.descent()
            painter.drawText(x, int(baseline_1), elided_filename)

            # 5. Draw second line (folder path)
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
