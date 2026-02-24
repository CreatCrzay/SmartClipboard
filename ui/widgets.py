"""
Custom UI widgets
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFrame, QLabel, QVBoxLayout, QMenu
from PySide6.QtGui import QPainter, QColor, QAction, QFont, QFontMetrics
from PySide6.QtCore import Qt, Signal, QPoint, QEvent

from constants import (
    COLOR_BACKGROUND, COLOR_TEXT_PRIMARY, COLOR_BUTTON_HOVER, COLOR_BORDER,
    COLOR_PINNED_BORDER, PADDING, SPACING, BORDER_RADIUS, BORDER_WIDTH,
    CARD_INTERNAL_CONTENT_PADDING, CARD_INTERNAL_SPACING, CARD_HEIGHT_FIXED,
    CARD_WIDTH_FIXED, FONT_SIZE_CARD_CONTENT, FONT_FAMILY_ENGLISH,
    FONT_FAMILY_CHINESE, SCROLLBAR_WIDTH, ICON_FILE
)
from ui.styles import get_title_bar_style, get_clipboard_card_style, get_context_menu_style
from core.image_cache import get_cached_scaled_image


class FloatingScrollBar(QWidget):
    """
    Custom scrollbar component
    Logic:
    1. Remove auto-hide and opacity animation
    2. Always show when content exceeds view, hide otherwise
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SCROLLBAR_WIDTH)
        self._scroll_bar = None
        self._is_hovering = False
        self._is_dragging = False
        self._drag_start_pos = 0
        self._drag_start_scroll_value = 0

        # Hide by default, wait for scroll bar binding
        self.hide()

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.ArrowCursor)

    def set_scroll_bar(self, scroll_bar):
        """Bind to target scroll bar"""
        self._scroll_bar = scroll_bar
        if self._scroll_bar:
            self._scroll_bar.valueChanged.connect(self.update)
            self._scroll_bar.rangeChanged.connect(self._on_range_changed)
            # Check status on init
            self._on_range_changed(self._scroll_bar.minimum(), self._scroll_bar.maximum())
            self._scroll_bar.installEventFilter(self)

    def _on_range_changed(self, min_val, max_val):
        """
        Core logic:
        Show scrollbar when max_val > min_val (content exceeds view)
        Hide otherwise
        """
        if max_val > min_val:
            self.show()
        else:
            self.hide()
        self.update()

    def paintEvent(self, event):
        """Paint scrollbar"""
        if not self._scroll_bar:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate slider position and size
        bar_height = self.height()
        max_val = self._scroll_bar.maximum()
        page_step = self._scroll_bar.pageStep()

        if max_val <= 0:
            return

        # 1. Calculate slider height
        slider_ratio = page_step / (max_val + page_step)
        slider_height = max(int(bar_height * slider_ratio), 20)

        # 2. Calculate slider position
        scroll_ratio = self._scroll_bar.value() / max_val
        slider_pos = int((bar_height - slider_height) * scroll_ratio)

        # 3. Set slider color
        if self._is_dragging:
            color = QColor(160, 160, 160)
        elif self._is_hovering:
            color = QColor(120, 120, 120)
        else:
            color = QColor(80, 80, 80)

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)

        # Draw rounded rectangle slider
        painter.drawRoundedRect(0, slider_pos, self.width(), slider_height, self.width() // 2, self.width() // 2)

    def enterEvent(self, event):
        """Mouse enter, change color"""
        self._is_hovering = True
        self.update()

    def leaveEvent(self, event):
        """Mouse leave, restore color"""
        self._is_hovering = False
        self.update()

    def mousePressEvent(self, event):
        """Mouse press"""
        if event.button() == Qt.LeftButton and self._scroll_bar:
            click_y = event.position().y()
            bar_height = self.height()
            max_val = self._scroll_bar.maximum()
            page_step = self._scroll_bar.pageStep()

            if max_val <= 0:
                return

            slider_ratio = page_step / (max_val + page_step)
            slider_height = max(int(bar_height * slider_ratio), 20)

            scroll_range = bar_height - slider_height
            if scroll_range <= 0:
                return

            slider_pos = int(scroll_range * (self._scroll_bar.value() / max_val))

            # Check if clicked on slider or track
            if slider_pos <= click_y <= slider_pos + slider_height:
                # Clicked on slider - start dragging
                self._is_dragging = True
                self._drag_start_pos = click_y
                self._drag_start_scroll_value = self._scroll_bar.value()
            else:
                # Clicked on track - quick scroll
                click_ratio = max(0.0, min(1.0, (click_y - slider_height / 2) / scroll_range))
                new_value = int(max_val * click_ratio)
                self._scroll_bar.setValue(new_value)

            self.update()

    def mouseMoveEvent(self, event):
        """Mouse drag"""
        if self._is_dragging and self._scroll_bar:
            current_y = event.position().y()
            delta_y = current_y - self._drag_start_pos

            bar_height = self.height()
            max_val = self._scroll_bar.maximum()
            page_step = self._scroll_bar.pageStep()

            slider_ratio = page_step / (max_val + page_step)
            slider_height = max(int(bar_height * slider_ratio), 20)
            scroll_range = bar_height - slider_height

            if scroll_range > 0:
                scroll_delta = int(delta_y * max_val / scroll_range)
                new_value = self._drag_start_scroll_value + scroll_delta
                new_value = max(0, min(max_val, new_value))
                self._scroll_bar.setValue(new_value)

    def mouseReleaseEvent(self, event):
        """Mouse release"""
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.update()

    def eventFilter(self, obj, event):
        """Event filter, handle target control show/hide"""
        if obj == self._scroll_bar:
            if event.type() == QEvent.Type.Show:
                self._on_range_changed(self._scroll_bar.minimum(), self._scroll_bar.maximum())
            elif event.type() == QEvent.Type.Hide:
                self.hide()
        return super().eventFilter(obj, event)


class TitleBar(QWidget):
    settings_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("title_bar")
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        # Margin aligned with card content
        content_margin = PADDING + CARD_INTERNAL_CONTENT_PADDING
        layout.setContentsMargins(content_margin, content_margin, content_margin, 4)
        layout.setSpacing(SPACING)

        self.settings_button = QPushButton("设置")
        button_font = QFont(FONT_FAMILY_CHINESE)
        button_font.setPixelSize(14)
        button_font.setBold(True)
        self.settings_button.setFont(button_font)
        self.settings_button.setFixedSize(32, 20)
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self.settings_button.setObjectName("settings_button")

        self.close_button = QPushButton("关闭")
        close_font = QFont(FONT_FAMILY_CHINESE)
        close_font.setPixelSize(14)
        close_font.setBold(True)
        self.close_button.setFont(close_font)
        self.close_button.setFixedSize(32, 20)
        self.close_button.clicked.connect(self.close_requested.emit)
        self.close_button.setObjectName("close_button")

        layout.addWidget(self.settings_button)
        layout.addStretch(1)
        layout.addWidget(self.close_button)

        self.setStyleSheet(get_title_bar_style())


class ClipboardCard(QFrame):
    """
    Legacy card widget (retained for compatibility, but currently unused).
    The app now uses QListView + ClipboardDelegate for better performance.
    """
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
        if not path:
            return ""
        metrics = self._get_font_metrics()
        if metrics.horizontalAdvance(path) <= max_width:
            return path

        ellipsis_text = "..."
        ellipsis_width = metrics.horizontalAdvance(ellipsis_text)
        if max_width <= ellipsis_width:
            return ellipsis_text

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
        import json
        from PySide6.QtCore import QRunnable, QThreadPool, QMetaObject, Qt as QtCoreQt
        from PySide6.QtGui import QImage
        from PySide6.QtCore import QByteArray

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
                        if i >= max_lines:
                            break
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
                            if not display_filename.endswith("..."):
                                display_filename += "..."
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
        from PySide6.QtCore import QRunnable, QThreadPool, QMetaObject, Qt as QtCoreQt

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
                            QtCoreQt.QueuedConnection,
                            Q_ARG(object, self.label), Q_ARG(object, pixmap)
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
