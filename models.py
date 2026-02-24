"""
Clipboard data model (Qt Model)
"""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QFont, QFontMetrics

from constants import FONT_SIZE_CARD_CONTENT, FONT_FAMILY_ENGLISH


class ClipboardModel(QAbstractListModel):
    """Clipboard data model (Qt Model)"""

    # Custom role enums
    RoleId = Qt.UserRole + 1
    RoleType = Qt.UserRole + 2
    RoleContent = Qt.UserRole + 3
    RoleIsPinned = Qt.UserRole + 4
    RoleContentPreview = Qt.UserRole + 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clips = []  # Store (id, type, content, is_pinned) tuples
        self._id_to_row = {}  # id -> row index mapping for fast lookup

    def rowCount(self, parent=None):
        return len(self._clips)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._clips):
            return None

        clip = self._clips[index.row()]
        clip_id, clip_type, clip_content, is_pinned = clip

        if role == Qt.DisplayRole:
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
        """Get content preview text"""
        import json
        import os
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
        Set new data list
        clips: [(id, type, content, is_pinned), ...]
        """
        self.beginResetModel()
        self._clips = clips
        self._id_to_row = {clip[0]: i for i, clip in enumerate(clips)}
        self.endResetModel()

    def get_clip_by_id(self, clip_id):
        """Get clip data by ID"""
        row = self._id_to_row.get(clip_id)
        if row is not None and row < len(self._clips):
            return self._clips[row]
        return None

    def get_row_by_id(self, clip_id):
        """Get row index by ID"""
        return self._id_to_row.get(clip_id)

    def remove_row_by_id(self, clip_id):
        """Remove row by ID"""
        row = self._id_to_row.get(clip_id)
        if row is not None:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._clips[row]
            # Rebuild id -> row mapping
            self._id_to_row = {clip[0]: i for i, clip in enumerate(self._clips)}
            self.endRemoveRows()
            return True
        return False

    def update_row_by_id(self, clip_id):
        """Trigger data update signal for a row"""
        row = self._id_to_row.get(clip_id)
        if row is not None:
            index = self.index(row)
            self.dataChanged.emit(index, index)
