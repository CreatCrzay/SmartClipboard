"""
Settings dialog
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QCheckBox, QComboBox,
    QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from constants import COLOR_BACKGROUND, COLOR_BORDER, BORDER_RADIUS
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
