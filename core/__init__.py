"""
Core functionality package
"""
from .image_cache import ImageCache, image_cache, get_cached_scaled_image
from .windows_internals import (
    HotkeyHookWorker, WinHotkeyListener, WindowHistoryManager, AutoConfigManager
)

__all__ = [
    'ImageCache', 'image_cache', 'get_cached_scaled_image',
    'HotkeyHookWorker', 'WinHotkeyListener', 'WindowHistoryManager', 'AutoConfigManager'
]
