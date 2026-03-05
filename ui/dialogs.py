"""
Settings dialog and Preview dialog
"""
import json
import base64

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QCheckBox, QComboBox,
    QPushButton, QSizePolicy, QTextEdit, QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QByteArray
from PySide6.QtGui import QImage, QPixmap

from constants import (
    COLOR_BACKGROUND, COLOR_BORDER, BORDER_RADIUS, COLOR_TEXT_PRIMARY,
    COLOR_CARD_BG, PADDING, SPACING
)
from ui.styles import get_settings_dialog_style


class SettingsDialog(QDialog):
    settings_changed = Signal()

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setModal(True)
        self.setFixedSize(220, 160)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        # Enable transparent background for rounded corners
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._init_ui()
        self._load_settings_to_ui()
        self.setStyleSheet(get_settings_dialog_style())

    def _init_ui(self):
        # Container widget for actual content area
        self.container_widget = QWidget(self)
        self.container_widget.setObjectName("settings_container")

        # Main layout with transparent background
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container_widget)

        # Content layout added to container
        layout = QVBoxLayout(self.container_widget)
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
        if days <= 0.01:
            return 0
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


class PreviewDialog(QDialog):
    """Preview dialog for text and image content"""

    # Fixed size
    DIALOG_WIDTH = 400
    DIALOG_HEIGHT = 400

    def __init__(self, clip_type, content, parent=None, auto_hide=False):
        super().__init__(parent)
        self.clip_type = clip_type
        self.content = content
        self.auto_hide = auto_hide
        self.setWindowTitle("预览")
        self.setFixedSize(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)

        # Use Qt.Dialog to make it a child dialog, auto-hide will be handled by parent
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)

        # Store relative position for following parent window
        self._relative_pos = None

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._init_ui()
        self._load_content()
        self.setStyleSheet(self._get_style())

    def _init_ui(self):
        """Initialize UI"""
        # Container widget
        self.container_widget = QWidget(self)
        self.container_widget.setObjectName("preview_container")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container_widget)

        layout = QVBoxLayout(self.container_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)

        # Content area (fills entire space for equal borders)
        self.content_area = QScrollArea()
        self.content_area.setWidgetResizable(True)
        self.content_area.setFrameShape(QFrame.NoFrame)
        self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Text content
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFrameShape(QFrame.NoFrame)
        self.text_edit.setObjectName("preview_text_edit")
        self.text_edit.hide()
        self.content_layout.addWidget(self.text_edit)

        # Image content
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setObjectName("preview_image_label")
        self.image_label.hide()
        self.content_layout.addWidget(self.image_label)

        self.content_area.setWidget(self.content_widget)
        layout.addWidget(self.content_area)

        # Enable mouse tracking for image zoom
        self.content_area.viewport().setMouseTracking(True)
        self.content_area.viewport().installEventFilter(self)

        # Image zoom state
        self._original_pixmap = None
        self._current_scale = 1.0
        self._min_scale = 0.1
        self._max_scale = 5.0

    def _load_content(self):
        """Load content based on type"""
        if self.clip_type == "TEXT":
            self._load_text()
        elif self.clip_type == "IMAGE":
            self._load_image()
        elif self.clip_type == "FILES":
            self._load_files()

    def _load_text(self):
        """Load text content"""
        self.text_edit.setPlainText(self.content)
        self.text_edit.show()
        self.image_label.hide()

    def _load_image(self):
        """Load image content and scale to fit window"""
        try:
            image_data_b64 = self.content
            try:
                data = json.loads(self.content)
                if isinstance(data, dict) and "image_data" in data:
                    image_data_b64 = data["image_data"]
            except json.JSONDecodeError:
                pass

            self.original_image = QImage()
            if self.original_image.loadFromData(QByteArray.fromBase64(image_data_b64.encode('utf-8'))):
                self._original_pixmap = QPixmap.fromImage(self.original_image)
                # Reset scale
                self._current_scale = 1.0
                # Apply initial fit-to-window scaling
                self._fit_image_to_window()
                self.image_label.show()
                self.text_edit.hide()
            else:
                self._show_error("无法加载图像")
        except Exception as e:
            self._show_error(f"图像加载失败: {str(e)}")

    def _fit_image_to_window(self):
        """Scale image to fit window initially"""
        if not self._original_pixmap:
            return

        # Calculate available space (accounting for padding)
        available_width = self.DIALOG_WIDTH - (PADDING * 2) - 20
        available_height = self.DIALOG_HEIGHT - (PADDING * 2) - 20

        # Calculate scale to fit
        img_width = self._original_pixmap.width()
        img_height = self._original_pixmap.height()

        scale_x = available_width / img_width if img_width > 0 else 1
        scale_y = available_height / img_height if img_height > 0 else 1

        # Use the smaller scale to fit entirely
        self._current_scale = min(scale_x, scale_y, 1.0)

        self._update_image_display()

    def _update_image_display(self):
        """Update image display with current scale"""
        if not self._original_pixmap:
            return

        new_width = int(self._original_pixmap.width() * self._current_scale)
        new_height = int(self._original_pixmap.height() * self._current_scale)

        scaled_pixmap = self._original_pixmap.scaled(
            new_width, new_height,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

    def _load_files(self):
        """Load file list content"""
        try:
            data = json.loads(self.content)
            paths = data.get("original_paths", [])
            text = "文件列表:\n\n"
            for i, path in enumerate(paths, 1):
                text += f"{i}. {path}\n"
            self.text_edit.setPlainText(text)
            self.text_edit.show()
            self.image_label.hide()
        except Exception as e:
            self._show_error(f"文件解析失败: {str(e)}")

    def _show_error(self, message):
        """Show error message"""
        self.text_edit.setPlainText(message)
        self.text_edit.show()
        self.image_label.hide()

    def _get_style(self):
        """Get dialog stylesheet"""
        return f"""
            #preview_container {{
                background-color: {COLOR_BACKGROUND};
                border: 1px solid {COLOR_BORDER};
                border-radius: {BORDER_RADIUS}px;
            }}
            #preview_text_edit {{
                background-color: {COLOR_CARD_BG};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
                font-family: Consolas, "微软雅黑", monospace;
            }}
            #preview_image_label {{
                background-color: {COLOR_CARD_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLOR_BORDER};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: #606060;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: transparent;
                height: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {COLOR_BORDER};
                border-radius: 4px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: #606060;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """

    def mousePressEvent(self, event):
        """Handle mouse press for dragging"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging"""
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def keyPressEvent(self, event):
        """Close on Escape key"""
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def is_mouse_inside(self):
        """Check if mouse cursor is inside the dialog"""
        from PySide6.QtGui import QCursor
        return self.geometry().contains(QCursor.pos())

    def eventFilter(self, obj, event):
        """Handle wheel events for image zooming"""
        if obj == self.content_area.viewport() and event.type() == event.Type.Wheel:
            if self.clip_type == "IMAGE" and self._original_pixmap:
                # Get wheel delta
                delta = event.angleDelta().y()

                # Calculate zoom factor
                if delta > 0:
                    zoom_factor = 1.1
                else:
                    zoom_factor = 0.9

                # Calculate new scale
                new_scale = self._current_scale * zoom_factor

                # Clamp to min/max
                new_scale = max(self._min_scale, min(self._max_scale, new_scale))

                # Update scale if changed
                if new_scale != self._current_scale:
                    self._current_scale = new_scale
                    self._update_image_display()

                event.accept()
                return True

        return super().eventFilter(obj, event)
