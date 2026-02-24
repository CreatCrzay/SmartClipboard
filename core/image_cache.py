import hashlib
import json
import os
import sys
from collections import OrderedDict
from threading import Lock

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QImage, QPixmap


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
    """Get cached scaled image"""
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
