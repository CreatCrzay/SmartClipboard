import sys
import os
import json
import hashlib


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_app_data_path():
    """Get the application data directory."""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return application_path


def get_file_metadata_hash(file_path):
    """Generate a hash from file metadata for comparison."""
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
