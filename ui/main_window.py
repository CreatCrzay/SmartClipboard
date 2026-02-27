"""
Main window UI components
"""
import sys

from PySide6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit,
    QScrollArea, QListView, QStyle
)
from PySide6.QtCore import Qt, Signal, QPoint

from constants import (
    COLOR_BACKGROUND, COLOR_BUTTON_HOVER, PADDING, SPACING,
    BORDER_WIDTH, WINDOW_WIDTH, WINDOW_HEIGHT, CARD_INTERNAL_CONTENT_PADDING,
    SCROLLBAR_WIDTH, SCROLLBAR_SPACING
)
from ui.styles import get_main_window_style, get_search_bar_style, get_title_bar_style
from ui.widgets import FloatingScrollBar, TitleBar

# Optional Windows imports
try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None


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

        # Setup search bar
        self._setup_search_bar()
        self.main_layout.addWidget(self.search_bar_container)

        content_layout = QVBoxLayout()
        # Margin logic: side margins align with card content, bottom margin equals side margins
        content_margin = PADDING + CARD_INTERNAL_CONTENT_PADDING
        content_layout.setContentsMargins(
            PADDING,
            0,
            PADDING,
            content_margin
        )
        content_layout.setSpacing(SPACING)

        self._setup_card_area()
        content_layout.addWidget(self.scroll_container)
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
        """Setup search box"""
        self.search_bar_container = QWidget()
        self.search_bar_container.setObjectName("search_bar_container")
        search_bar_layout = QHBoxLayout(self.search_bar_container)
        search_bar_layout.setContentsMargins(0, 0, 0, 0)
        search_bar_layout.setSpacing(0)

        # Add left stretch
        search_bar_layout.addStretch()

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("搜索")
        self.search_bar.setFixedHeight(28)
        from constants import CARD_WIDTH_FIXED, CARD_INTERNAL_CONTENT_PADDING
        # 搜索框宽度 = 卡片宽度 - 两侧内部边距
        search_width = CARD_WIDTH_FIXED - (CARD_INTERNAL_CONTENT_PADDING * 2)+2
        self.search_bar.setFixedWidth(search_width)
        self.search_bar.setStyleSheet(get_search_bar_style())
        self.search_bar.setObjectName("search_bar")
        search_bar_layout.addWidget(self.search_bar)

        # Add right stretch
        search_bar_layout.addStretch()

        # Hidden by default
        self.search_bar_container.hide()
        return self.search_bar_container

    def _setup_card_area(self):
        # Container widget for scroll area
        self.scroll_container = QWidget()
        self.scroll_container.setObjectName("scroll_container")
        scroll_container_layout = QHBoxLayout(self.scroll_container)
        scroll_container_layout.setContentsMargins(0, 0, 0, 0)
        scroll_container_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Hide vertical scrollbar, use custom floating scrollbar
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Use QListView instead of card container
        self.list_view = QListView()
        self.list_view.setObjectName("list_view")
        self.list_view.setVerticalScrollMode(QListView.ScrollPerItem)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_view.setSpacing(SPACING)
        self.list_view.setCursor(Qt.PointingHandCursor)

        # 禁用鼠标自动跟踪，只有点击才选中
        self.list_view.setMouseTracking(True)  # 开启以显示悬浮效果，但delegate区分颜色
        self.list_view.setSelectionMode(QListView.SingleSelection)

        # Wheel event patch
        def custom_wheel_event(event):
            v_scrollbar = self.list_view.verticalScrollBar()
            delta = event.angleDelta().y()
            if delta == 0:
                return
            scroll_step = 2
            current_value = v_scrollbar.value()
            if delta > 0:
                new_value = max(0, current_value - scroll_step)
            else:
                new_value = min(v_scrollbar.maximum(), current_value + scroll_step)
            v_scrollbar.setValue(new_value)
            event.accept()

        self.list_view.wheelEvent = custom_wheel_event

        # Style
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
        scroll_container_layout.addWidget(self.scroll_area)

        # Floating scrollbar
        self.floating_scrollbar = FloatingScrollBar(self)
        self.floating_scrollbar.set_scroll_bar(self.list_view.verticalScrollBar())
        self.floating_scrollbar.raise_()

        # Update position function
        def update_scrollbar_geometry():
            if not hasattr(self, 'floating_scrollbar') or not self.floating_scrollbar:
                return

            container_pos = self.scroll_container.mapTo(self, QPoint(0, 0))

            # X: place at right edge
            x = self.width() - SCROLLBAR_WIDTH - 2

            # Y: add SPACING offset for visual alignment with card top
            y = container_pos.y() + SPACING

            # Height: subtract (SPACING * 2) for top and bottom gaps
            h = self.scroll_container.height() - (SPACING * 2)

            self.floating_scrollbar.setGeometry(x, y, SCROLLBAR_WIDTH, h)

        # Bind events
        self.scroll_container.resizeEvent = lambda event: update_scrollbar_geometry()
        self.scroll_container.moveEvent = lambda event: update_scrollbar_geometry()

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
