"""
SmartClipboard - Main application entry point
"""
import sys
from PySide6.QtWidgets import QApplication

from core.windows_internals import AutoConfigManager
from ui.main_app import SmartClipboardApp


def main():
    # Check auto-start configuration
    config_manager = AutoConfigManager()
    config_manager.setup_auto_start()

    app = QApplication(sys.argv)
    app.setApplicationName("SmartClipboard")

    window = SmartClipboardApp()
    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
