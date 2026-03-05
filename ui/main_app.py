"""
Main application class - SmartClipboardApp
Contains all business logic for clipboard management
"""
import base64
import datetime
import json
import logging
import os
import re
import shutil
import sys

from PySide6.QtWidgets import (
    QApplication, QMessageBox, QFileDialog, QMenu
)
from PySide6.QtGui import QAction, QKeyEvent, QImage, QImage, QCursor
from PySide6.QtCore import (
    Qt, QTimer, QByteArray, QMimeData, QUrl, QThreadPool, QRunnable,
    QMetaObject, Q_ARG, QEvent, QItemSelectionModel, QBuffer, QRect
)
from PySide6.QtCore import QSortFilterProxyModel

from constants import TEMP_DIR_NAME, COLOR_BACKGROUND, COLOR_BUTTON_HOVER
from utils import get_app_data_path, get_file_metadata_hash
from settings import SettingsManager
from database import DatabaseManager
from models import ClipboardModel
from core.image_cache import get_cached_scaled_image, image_cache
from core.windows_internals import WinHotkeyListener, WindowHistoryManager
from ui.main_window import MainWindowUI
from ui.dialogs import SettingsDialog, PreviewDialog
from ui.delegate import ClipboardDelegate
from ui.styles import get_context_menu_style, get_message_box_style

# Optional Windows imports
try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

from pynput.keyboard import Controller


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

        # Preview dialog (manual trigger only)
        self._current_preview_dialog = None
        self._preview_source_index = None  # 记录触发预览的卡片索引
        self._preview_hide_delay_ms = 300  # 延迟关闭时间（毫秒）
        self._preview_check_interval_ms = 100  # 鼠标位置检测间隔
        self._preview_hide_timer = QTimer(self)
        self._preview_hide_timer.setSingleShot(True)
        self._preview_hide_timer.timeout.connect(self._hide_preview_dialog)
        self._preview_mouse_timer = QTimer(self)
        self._preview_mouse_timer.timeout.connect(self._check_preview_should_hide)
        self._last_main_pos = None  # 用于检测主窗口移动

        # Initialize Model and Delegate
        self.model = ClipboardModel(self)
        self.delegate = ClipboardDelegate(self)

        # Setup search filter
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterRole(ClipboardModel.RoleContentPreview)

        # Bind to View
        self.list_view.setModel(self.proxy_model)
        self.list_view.setItemDelegate(self.delegate)

        # Handle click events
        self.list_view.clicked.connect(self._on_list_item_clicked)

        # Handle context menu
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)

        self._setup_persistence_dirs()
        QApplication.instance().aboutToQuit.connect(self._cleanup_on_quit)

        self.settings_requested.connect(self._on_settings_requested)
        self.error_message_requested.connect(self._show_error_message_ui)
        self.info_message_requested.connect(self._show_info_message_ui)
        self.warning_message_requested.connect(self._show_warning_message_ui)
        self.question_message_requested.connect(self._show_question_message_ui_slot)

        # Connect search box signals
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        self.search_bar.returnPressed.connect(self._on_search_return_pressed)

        # Install event filters for Ctrl+F shortcut
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

        # Handle Enter key for pasting
        self._original_list_key_press = self.list_view.keyPressEvent

        def custom_list_key_press(event):
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                index = self.list_view.currentIndex()
                if index.isValid():
                    self._on_list_item_clicked(index)
                event.accept()
            elif key == Qt.Key_Down:
                # If no item is selected, select the first one
                current_index = self.list_view.currentIndex()
                if not current_index.isValid() and self.proxy_model.rowCount() > 0:
                    first_index = self.proxy_model.index(0, 0)
                    if first_index.isValid():
                        self.list_view.setCurrentIndex(first_index)
                        self.list_view.selectionModel().select(
                            first_index,
                            QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
                        )
                    event.accept()
                else:
                    self._original_list_key_press(event)
            else:
                self._original_list_key_press(event)

        self.list_view.keyPressEvent = custom_list_key_press

    def eventFilter(self, obj, event):
        """Event filter for Ctrl+F shortcut and Escape key in search box"""
        if event.type() == QEvent.Type.KeyPress:
            key_event = QKeyEvent(event)
            if key_event.key() == Qt.Key_F and (key_event.modifiers() & Qt.ControlModifier):
                self._toggle_search_bar()
                return True
            # Handle Escape key in search box
            if obj == self.search_bar and key_event.key() == Qt.Key_Escape:
                self._on_search_escape()
                return True
        return super().eventFilter(obj, event)

    def _toggle_search_bar(self):
        """Toggle search bar visibility"""
        if self.search_bar_container.isVisible():
            self.search_bar_container.hide()
            self.search_bar.clear()
            self.proxy_model.setFilterFixedString("")
        else:
            self.search_bar_container.show()
            self.search_bar.setFocus()
            self.search_bar.selectAll()

    def _on_search_text_changed(self, text):
        """Handle search text change"""
        self.proxy_model.setFilterFixedString(text)
        # Select first item if there are results
        if self.proxy_model.rowCount() > 0:
            first_index = self.proxy_model.index(0, 0)
            if first_index.isValid():
                self.list_view.setCurrentIndex(first_index)
                self.list_view.selectionModel().select(
                    first_index,
                    QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
                )

    def _on_search_return_pressed(self):
        """Paste selected item when pressing Enter in search box"""
        current_index = self.list_view.currentIndex()
        if current_index.isValid():
            source_index = self.proxy_model.mapToSource(current_index)
            if source_index.isValid():
                self._on_list_item_clicked(source_index)

    def _clear_search_state(self):
        """Clear search state: hide search box, clear text, reset filter"""
        self.search_bar_container.hide()
        self.search_bar.clear()
        self.proxy_model.setFilterFixedString("")
        self.list_view.setFocus()

    def _on_search_escape(self):
        """Hide search box when pressing Escape"""
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
        import hashlib
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
        import hashlib
        if clip_type == "FILES":
            try:
                content_obj = json.loads(serialized_content)
                return content_obj.get("metadata_hash")
            except json.JSONDecodeError:
                return hashlib.md5(serialized_content.encode('utf-8')).hexdigest()
        else:
            return self._calculate_hash(clip_type, serialized_content)

    def _process_new_system_clipboard_content(self, clip_type, serialized_content):
        # Deduplication logic
        duplicate_clip_id = None
        current_clip_hash = self._get_content_hash(clip_type, serialized_content)

        # Check for duplicates in Model
        for i, clip in enumerate(self.model._clips):
            clip_id, clip_type_in_model, clip_content_in_model, is_pinned = clip
            if not is_pinned:
                card_clip_hash = self._get_content_hash(clip_type_in_model, clip_content_in_model)
                if card_clip_hash == current_clip_hash:
                    duplicate_clip_id = clip_id
                    break

        # Delete duplicate
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

        # Reload data
        self.load_clips_from_db()

        if self.isVisible():
            self.update()
            QApplication.processEvents()

    def _normalize_text(self, text):
        if not text:
            return ""
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.rstrip()
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    def _extract_clipboard_data(self, mime_data):
        import html2text
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
                    if is_self_copy:
                        break

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

                import hashlib
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
        Override: no longer manually create Cards, query data for Model instead
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

        # Get data and refresh Model
        clips = self.db_manager.get_all_clips()
        self.model.set_data_list(clips)

        # Scroll to top
        if self.list_view.verticalScrollBar():
            self.list_view.verticalScrollBar().setValue(0)

        # Reapply filter if search text exists
        if self.search_bar_container.isVisible() and self.search_bar.text():
            self.proxy_model.setFilterFixedString(self.search_bar.text())
            if self.proxy_model.rowCount() > 0:
                first_index = self.proxy_model.index(0, 0)
                if first_index.isValid():
                    self.list_view.setCurrentIndex(first_index)

    def _on_list_item_clicked(self, index):
        """Handle list item click"""
        if not index.isValid():
            return

        # Convert proxy model index to source model index
        if isinstance(index.model(), QSortFilterProxyModel):
            index = self.proxy_model.mapToSource(index)
            if not index.isValid():
                return

        clip_id = index.data(ClipboardModel.RoleId)
        clip_type = index.data(ClipboardModel.RoleType)
        content = index.data(ClipboardModel.RoleContent)

        self._perform_paste_logic(clip_id, clip_type, content)

    def _perform_paste_logic(self, clip_id, clip_type, content):
        """Execute paste logic"""
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
                self._clear_search_state()
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
        """Handle context menu"""
        index = self.list_view.indexAt(pos)
        if not index.isValid():
            return

        clip_id = index.data(ClipboardModel.RoleId)
        is_pinned = index.data(ClipboardModel.RoleIsPinned)
        clip_type = index.data(ClipboardModel.RoleType)

        menu = QMenu(self)
        menu.setStyleSheet(get_context_menu_style())

        # Add preview action
        action_preview = menu.addAction("预览")
        menu.addSeparator()

        pin_text = "取消置顶" if is_pinned else "置顶"
        action_pin = menu.addAction(pin_text)
        action_export = menu.addAction("导出")
        action_delete = menu.addAction("删除")

        action = menu.exec(self.list_view.mapToGlobal(pos))

        if action == action_preview:
            self._on_card_preview(index)
        elif action == action_pin:
            self._on_card_pin_toggled(clip_id, is_pinned)
        elif action == action_export:
            self._on_card_export(clip_id)
        elif action == action_delete:
            self._on_card_delete(clip_id)

    def _on_card_delete(self, clip_id):
        """Delete clipboard item by ID"""
        reply = self.show_question_message("确认删除", "确定要删除该剪贴板内容吗？")
        if reply == QMessageBox.Yes:
            if self.db_manager.delete_clip(clip_id):
                self.model.remove_row_by_id(clip_id)

    def _hide_preview_dialog(self):
        """Hide and destroy the preview dialog"""
        # Stop timers first
        if self._preview_mouse_timer.isActive():
            self._preview_mouse_timer.stop()
        if self._preview_hide_timer.isActive():
            self._preview_hide_timer.stop()

        if self._current_preview_dialog:
            self._current_preview_dialog.hide()
            self._current_preview_dialog.deleteLater()
            self._current_preview_dialog = None
            self._preview_source_index = None

    def _on_card_preview(self, index):
        """Show preview dialog for clipboard item (manual trigger)"""
        if not index.isValid():
            return

        # Convert proxy model index to source model index if needed
        if isinstance(index.model(), QSortFilterProxyModel):
            index = self.proxy_model.mapToSource(index)
            if not index.isValid():
                return

        clip_type = index.data(ClipboardModel.RoleType)
        content = index.data(ClipboardModel.RoleContent)

        # Hide any existing preview first
        self._hide_preview_dialog()

        # Show preview dialog
        self._current_preview_dialog = PreviewDialog(clip_type, content, self, auto_hide=False)
        self._preview_source_index = index  # 记录触发预览的卡片索引

        # Position dialog next to main window
        self._update_preview_position()
        self._current_preview_dialog.show()

        # Start mouse position monitoring for auto-hide
        self._last_main_pos = self.pos()
        self._preview_mouse_timer.start(self._preview_check_interval_ms)

    def _update_preview_position(self):
        """Update preview dialog position relative to main window"""
        if not self._current_preview_dialog:
            return

        main_geo = self.geometry()
        preview_x = main_geo.right() + 10
        preview_y = main_geo.top()

        # Ensure dialog stays on screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.geometry()
            dialog_size = self._current_preview_dialog.size()
            if preview_x + dialog_size.width() > screen_geo.right():
                # Position to the left of main window
                preview_x = main_geo.left() - dialog_size.width() - 10
            if preview_y + dialog_size.height() > screen_geo.bottom():
                preview_y = screen_geo.bottom() - dialog_size.height() - 10
            if preview_y < screen_geo.top():
                preview_y = screen_geo.top() + 10

        self._current_preview_dialog.move(preview_x, preview_y)

    def _check_preview_should_hide(self):
        """Check if mouse has left main window + preview window area"""
        if not self._current_preview_dialog:
            self._preview_mouse_timer.stop()
            return

        # Check if main window has moved, update preview position
        if self._last_main_pos != self.pos():
            self._last_main_pos = self.pos()
            self._update_preview_position()

        mouse_pos = QCursor.pos()
        main_geo = self.geometry()
        preview_geo = self._current_preview_dialog.geometry()

        # Check if mouse is in preview window
        in_preview = preview_geo.contains(mouse_pos)
        # Check if mouse is in bridge area between windows
        in_bridge = self._is_in_bridge_area(mouse_pos, main_geo, preview_geo)
        # Check if mouse is on the source card (the card that triggered preview)
        in_source_card = self._is_in_source_card(mouse_pos)

        if not in_source_card and not in_preview and not in_bridge:
            # Mouse left all areas, start hide delay if not already started
            if not self._preview_hide_timer.isActive():
                self._preview_hide_timer.start(self._preview_hide_delay_ms)
        else:
            # Mouse is in one of the areas, cancel hide delay
            if self._preview_hide_timer.isActive():
                self._preview_hide_timer.stop()

    def _is_in_bridge_area(self, pos, main_geo, preview_geo):
        """Check if mouse is in bridge area between main and preview windows"""
        # Determine if preview is on left or right of main window
        if preview_geo.center().x() > main_geo.center().x():
            # Preview on right
            bridge_left = main_geo.right()
            bridge_right = preview_geo.left()
        else:
            # Preview on left
            bridge_left = preview_geo.right()
            bridge_right = main_geo.left()

        # Vertical overlap with some margin
        bridge_top = max(main_geo.top(), preview_geo.top()) - 20
        bridge_bottom = min(main_geo.bottom(), preview_geo.bottom()) + 20

        # Ensure left < right
        if bridge_left > bridge_right:
            bridge_left, bridge_right = bridge_right, bridge_left

        return (bridge_left <= pos.x() <= bridge_right and
                bridge_top <= pos.y() <= bridge_bottom)

    def _is_in_source_card(self, pos):
        """Check if mouse is on the source card that triggered the preview"""
        if not self._preview_source_index or not self._preview_source_index.isValid():
            return False

        # Get the visual rectangle of the source card in the list view
        # Note: _preview_source_index is a source model index, need to map to proxy
        proxy_index = self.proxy_model.mapFromSource(self._preview_source_index)
        if not proxy_index.isValid():
            return False

        # Get the visual rect of this item in the list view
        card_rect = self.list_view.visualRect(proxy_index)
        # Map to global coordinates
        top_left_global = self.list_view.mapToGlobal(card_rect.topLeft())
        bottom_right_global = self.list_view.mapToGlobal(card_rect.bottomRight())
        card_rect_global = QRect(top_left_global, bottom_right_global)

        return card_rect_global.contains(pos)

    def _on_card_pin_toggled(self, clip_id, current_pin_status):
        """Toggle pin status"""
        new_status = not current_pin_status
        if self.db_manager.toggle_pin_status(clip_id, new_status):
            self.load_clips_from_db()

    def _on_card_export(self, clip_id):
        """Export clipboard content by ID"""
        clip = self.model.get_clip_by_id(clip_id)
        if not clip:
            return

        clip_id, clip_type, content, is_pinned = clip

        if clip_type == "TEXT":
            file_path, _ = QFileDialog.getSaveFileName(self, "导出文本", "clipboard_export.txt", "Text Files (*.txt);;All Files (*)")
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
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
            except:
                pass

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
                if not paths:
                    return

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
                                if os.path.isdir(p):
                                    shutil.copytree(p, dest, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(p, dest)
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
        from PySide6.QtWidgets import QSystemTrayIcon
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QUrl
        from utils import resource_path

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
        tray_menu.setStyleSheet(get_context_menu_style())
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)

    def _on_tray_icon_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self.show_and_position_window_on_hotkey(from_tray=True, force_center=True)

    def quit_application(self):
        self.hide()

        if self.paste_timer.isActive():
            self.paste_timer.stop()
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()
            self.tray_icon = None
        if self.hotkey_listener:
            self.hotkey_listener.stop_listening()
        QApplication.quit()

    def _force_release_win_key(self):
        """Force release Win key if stuck"""
        try:
            import ctypes
            from ctypes import wintypes

            if (ctypes.windll.user32.GetAsyncKeyState(0x5B) & 0x8000) or \
               (ctypes.windll.user32.GetAsyncKeyState(0x5C) & 0x8000):

                class KEYBDINPUT(ctypes.Structure):
                    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                                ("dwExtraInfo", ctypes.c_void_p)]

                class INPUT(ctypes.Structure):
                    class _INPUT(ctypes.Union):
                        _fields_ = [("ki", KEYBDINPUT)]
                    _anonymous_ = ("_input",)
                    _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]

                inputs = (INPUT * 1)()
                inputs[0].type = 1
                inputs[0].ki.wVk = 0x5B
                inputs[0].ki.dwFlags = 2
                ctypes.windll.user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
                logging.info("Detected stuck Win key, forced release.")
        except Exception:
            pass

    def hideEvent(self, event):
        """Hide preview dialog immediately when main window is hidden"""
        super().hideEvent(event)
        self._hide_preview_dialog()

    def show_and_position_window_on_hotkey(self, from_tray=False, force_center=False):
        # 1. Force release Win key to prevent stuck state
        if not from_tray:
            self._force_release_win_key()

        # Clear search state when hiding window or opening from tray
        if self.isVisible():
            self._clear_search_state()

        if self._is_settings_dialog_open:
            return

        if self.isVisible():
            self.hide()
        else:
            # Clear search state when opening from tray
            if from_tray:
                self._clear_search_state()
            self.load_clips_from_db()
            screen = QApplication.primaryScreen()
            if not screen:
                screen = QApplication.screenAt(QCursor.pos())

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
            self.activateWindow()

            # Set focus to list view but do not auto-select any item
            self.list_view.setFocus()
            self.list_view.clearSelection()
            self.list_view.setCurrentIndex(self.proxy_model.index(-1, -1))
