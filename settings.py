import os
import json
import logging

from constants import SETTINGS_FILE


class SettingsManager:
    def __init__(self, current_dir):
        self.current_dir = current_dir
        self.settings_file = os.path.join(current_dir, SETTINGS_FILE)
        self.default_settings = {
            "auto_clean_days": 7,
            "auto_clean_enabled": False,
            "window_width": 270,
            "window_height": 390,
            "paste_as_file_enabled": False,
            "max_history_enabled": True,
            "max_history_count": 100,
            "create_copy_enabled": False,
        }
        self.settings = self.load_settings()

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    merged_settings = self.default_settings.copy()
                    merged_settings.update(settings)
                    for key, default_value in self.default_settings.items():
                        if key not in merged_settings:
                            merged_settings[key] = default_value
                    return merged_settings
            else:
                self.save_settings(self.default_settings)
                return self.default_settings.copy()
        except (OSError, IOError, json.JSONDecodeError):
            return self.default_settings.copy()

    def save_settings(self, settings):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            self.settings = settings
        except (OSError, IOError, TypeError):
            pass

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings(self.settings)
