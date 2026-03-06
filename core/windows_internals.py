"""
Windows internal functionality:
- Hotkey listener (Win+V)
- Window history management
- Auto-start configuration
"""

import ctypes
import logging
import os
import subprocess
import sys
import time
from ctypes import wintypes
from collections import deque

from PySide6.QtCore import QObject, QThread, Signal, QTimer

# Optional Windows Imports
try:
    import win32gui
    import win32con
    import win32process
except ImportError:
    win32gui = None
    win32con = None
    win32process = None

# ============================================================
# Hotkey Hook
# ============================================================

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_V = 0x56
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
    ]


class HotkeyHookWorker(QThread):
    hotkey_triggered = Signal()
    nav_key_pressed = Signal(int)  # 转发导航键: UP/DOWN/ENTER/ESCAPE, -1=取消拦截, -2=鼠标点击外部

    # 导航键虚拟键码
    VK_UP = 0x26
    VK_DOWN = 0x28
    VK_RETURN = 0x0D
    VK_ESCAPE = 0x1B
    VK_TAB = 0x09
    VK_MENU = 0x12  # Alt key
    VK_F = 0x46
    VK_CONTROL = 0x11

    def __init__(self, window_visible_callback=None, window_handle_callback=None):
        super().__init__()
        self.hook = None
        self.mouse_hook = None
        self.hook_proc = None
        self.mouse_hook_proc = None
        self._running = True
        self._v_pressed = False
        # Virtual key codes
        self.VK_V = 0x56
        self.VK_LWIN = 0x5B
        self.VK_RWIN = 0x5C
        # Use 0xFF as dummy key
        self.VK_DUMMY = 0xFF
        # 回调函数：检查窗口是否可见和获取窗口句柄
        self._window_visible_callback = window_visible_callback
        self._window_handle_callback = window_handle_callback
        # 导航拦截开关
        self._intercept_nav = False

    def run(self):
        self._setup_hooks()
        msg = wintypes.MSG()
        while self._running:
            try:
                # Use PeekMessage to keep message loop running
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                break
            time.sleep(0.005)

    def _setup_hooks(self):
        # 键盘钩子
        self.hook_proc = HOOKPROC(self._keyboard_hook_proc)
        self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.hook_proc, 0, 0)
        # 鼠标钩子
        self.mouse_hook_proc = HOOKPROC(self._mouse_hook_proc)
        self.mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self.mouse_hook_proc, 0, 0)

    def _send_dummy_key(self):
        """
        Send a dummy key event (0xFF) to trick Windows into thinking Win key
        is in combo state, preventing Start menu from appearing when Win is released.
        """
        try:
            user32.keybd_event(self.VK_DUMMY, 0, 0, 0)  # Dummy Down
            user32.keybd_event(self.VK_DUMMY, 0, 2, 0)  # Dummy Up
        except Exception:
            pass

    def _is_nav_key(self, vk_code):
        """检查是否是导航键"""
        return vk_code in (self.VK_UP, self.VK_DOWN, self.VK_RETURN, self.VK_ESCAPE)

    def _is_modifier_key(self, vk_code):
        """检查是否是修饰键（Ctrl, Shift, Alt, Win）"""
        return vk_code in (0x11, 0x12, 0x10, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)

    def _keyboard_hook_proc(self, nCode, wParam, lParam):
        try:
            if nCode >= 0:
                kb_data = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk_code = kb_data.vkCode

                # Detect message type
                is_down = (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN)
                is_up = (wParam == WM_KEYUP or wParam == WM_SYSKEYUP)

                # ========== 优先处理 Win+V（不受导航键拦截逻辑影响）==========
                if vk_code == self.VK_V:
                    if is_down:
                        # Check if Win key is pressed
                        win_pressed = (user32.GetAsyncKeyState(self.VK_LWIN) & 0x8000 != 0) or \
                                      (user32.GetAsyncKeyState(self.VK_RWIN) & 0x8000 != 0)

                        if win_pressed:
                            # Core logic: only trigger on first press (not repeat)
                            if not self._v_pressed:
                                self._v_pressed = True
                                self._send_dummy_key()  # Suppress start menu
                                self.hotkey_triggered.emit()  # Trigger business logic

                            # Intercept V key regardless
                            return 1

                    elif is_up:
                        # V key released, reset state
                        if self._v_pressed:
                            self._v_pressed = False
                            return 1

                # ========== 窗口可见时的导航键处理 ==========
                if self._window_visible_callback and self._window_visible_callback():
                    # 检测 Alt+Tab 或 Alt+Esc 等窗口切换组合键
                    if is_down:
                        alt_pressed = (user32.GetAsyncKeyState(self.VK_MENU) & 0x8000 != 0)
                        if alt_pressed and vk_code in (self.VK_TAB, self.VK_ESCAPE):
                            # 焦点即将离开，通知主程序取消拦截
                            self.nav_key_pressed.emit(-1)
                            return 0

                    # 只在启用拦截时才处理导航键
                    if self._intercept_nav:
                        # 检查是否按下 Ctrl 键
                        ctrl_pressed = (user32.GetAsyncKeyState(0x11) & 0x8000 != 0)

                        # 处理 Ctrl+F 搜索快捷键
                        if is_down and ctrl_pressed and vk_code == 0x46:  # F key
                            self.nav_key_pressed.emit(0x46)  # 发送 F 键信号表示 Ctrl+F
                            return 1  # 拦截按键

                        # 如果是导航键，拦截并处理
                        if is_down and self._is_nav_key(vk_code):
                            self.nav_key_pressed.emit(vk_code)
                            return 1  # 拦截按键

                        # 如果是非导航键且不是修饰键，取消拦截
                        # 但如果是带 Ctrl 的组合键，不取消拦截
                        if is_down and not self._is_nav_key(vk_code) and not self._is_modifier_key(vk_code):
                            if not ctrl_pressed:  # 只有不带 Ctrl 的按键才取消拦截
                                self.nav_key_pressed.emit(-1)  # 取消拦截
                                return 0  # 不拦截，让原窗口处理

        except Exception:
            pass
        return user32.CallNextHookEx(self.hook, nCode, wParam, lParam)

    def _mouse_hook_proc(self, nCode, wParam, lParam):
        """鼠标钩子处理：检测点击窗口外部"""
        try:
            if nCode >= 0 and self._intercept_nav and self._window_visible_callback and self._window_visible_callback():
                # 检查是否是鼠标点击事件
                if wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                    # 获取鼠标位置
                    class POINT(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                    pt = POINT()
                    user32.GetCursorPos(ctypes.byref(pt))

                    # 获取剪贴板窗口句柄
                    clipboard_hwnd = None
                    if self._window_handle_callback:
                        clipboard_hwnd = self._window_handle_callback()

                    if clipboard_hwnd and win32gui:
                        # 获取剪贴板窗口的区域
                        try:
                            rect = win32gui.GetWindowRect(clipboard_hwnd)
                            left, top, right, bottom = rect

                            # 检查鼠标是否在窗口外
                            if not (left <= pt.x <= right and top <= pt.y <= bottom):
                                # 点击了窗口外部，发送信号取消拦截
                                self.nav_key_pressed.emit(-2)  # -2 表示点击外部
                        except Exception:
                            pass
        except Exception:
            pass
        return user32.CallNextHookEx(self.mouse_hook, nCode, wParam, lParam)

    def stop_hook(self):
        self._running = False
        if self.hook:
            user32.UnhookWindowsHookEx(self.hook)
            self.hook = None
        if self.mouse_hook:
            user32.UnhookWindowsHookEx(self.mouse_hook)
            self.mouse_hook = None


class WinHotkeyListener(QObject):
    hotkeyPressed = Signal()
    navKeyPressed = Signal(int)  # 导航键信号

    def __init__(self, parent=None, window_visible_callback=None, window_handle_callback=None):
        super().__init__(parent)
        self.worker = None
        self._is_listening = False
        self._window_visible_callback = window_visible_callback
        self._window_handle_callback = window_handle_callback

    def start_listening(self):
        if not self._is_listening:
            self.worker = HotkeyHookWorker(self._window_visible_callback, self._window_handle_callback)
            self.worker.hotkey_triggered.connect(self._on_hotkey_pressed)
            self.worker.nav_key_pressed.connect(self._on_nav_key_pressed)
            self.worker.start()
            self._is_listening = True

    def stop_listening(self):
        if self._is_listening and self.worker:
            self.worker.hotkey_triggered.disconnect()
            self.worker.nav_key_pressed.disconnect()
            self.worker.stop_hook()
            self.worker.quit()
            self.worker.wait(3000)
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()
            self.worker = None
            self._is_listening = False

    def _on_hotkey_pressed(self):
        self.hotkeyPressed.emit()

    def _on_nav_key_pressed(self, vk_code):
        self.navKeyPressed.emit(vk_code)

    def enable_nav_intercept(self):
        """启用导航键拦截"""
        if self.worker:
            self.worker._intercept_nav = True

    def disable_nav_intercept(self):
        """禁用导航键拦截"""
        if self.worker:
            self.worker._intercept_nav = False


# ============================================================
# Window History Manager
# ============================================================

class WindowHistoryManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hwnd_history = deque(maxlen=4)
        self._last_hwnd = None
        self._app_main_window_hwnd = None

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._update_window_history)
        self._win32gui = None
        self._win32process = None
        if sys.platform == "win32":
            try:
                import win32gui
                import win32process
                self._win32gui = win32gui
                self._win32process = win32process
                logging.info("WindowHistoryManager: win32gui and win32process loaded.")
            except ImportError:
                pass
        self._system_window_classes = {
            "Shell_TrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow",
            "ApplicationFrameWindow", "TopLevelWindowForOverflowXamlIsland",
            "Qt5QWindowIcon", "Qt5QWindowOwnDCIcon", "SmartClipboard"
        }
        if parent and self._win32gui:
            try:
                self._app_main_window_hwnd = int(parent.winId())
            except Exception as e:
                self._app_main_window_hwnd = None

    def start_tracking(self):
        if self._win32gui:
            self._timer.start()

    def stop_tracking(self):
        self._timer.stop()

    def _get_window_title_and_process(self, hwnd):
        try:
            if self._win32gui and self._win32process:
                title = self._win32gui.GetWindowText(hwnd)
                _, pid = self._win32process.GetWindowThreadProcessId(hwnd)
                return title, pid
        except Exception:
            pass
        return "", 0

    def _get_window_class_name(self, hwnd):
        try:
            if self._win32gui:
                return self._win32gui.GetClassName(hwnd)
        except Exception:
            pass
        return ""

    def _is_valid_app_window(self, hwnd):
        if not self._win32gui or not hwnd:
            return False
        try:
            if not self._win32gui.IsWindowVisible(hwnd) or self._win32gui.IsIconic(hwnd):
                return False
            if hwnd == self._app_main_window_hwnd:
                return False
            class_name = self._get_window_class_name(hwnd)
            if class_name in self._system_window_classes:
                return False
            title = self._win32gui.GetWindowText(hwnd)
            if not title:
                return False
            if class_name.startswith("Qt") and not title:
                return False
            return True
        except Exception as e:
            return False

    def _update_window_history(self):
        if not self._win32gui:
            return
        try:
            current_hwnd = self._win32gui.GetForegroundWindow()
            if current_hwnd and current_hwnd != self._last_hwnd:
                if self._is_valid_app_window(current_hwnd):
                    self._last_hwnd = current_hwnd
                    self._hwnd_history.append(current_hwnd)
                else:
                    self._last_hwnd = current_hwnd
        except Exception as e:
            pass

    def restore_to_earliest_window(self):
        if not self._win32gui:
            return
        for i in range(len(self._hwnd_history) - 1, -1, -1):
            hwnd_to_restore = self._hwnd_history[i]
            try:
                if self._win32gui.IsWindow(hwnd_to_restore) and self._is_valid_app_window(hwnd_to_restore):
                    if self._win32gui.IsIconic(hwnd_to_restore):
                        self._win32gui.ShowWindow(hwnd_to_restore, 9)
                    else:
                        self._win32gui.ShowWindow(hwnd_to_restore, 5)
                    self._win32gui.SetForegroundWindow(hwnd_to_restore)
                    return
            except Exception as e:
                continue


# ============================================================
# Auto-start Configuration Manager
# ============================================================

class AutoConfigManager:
    """Auto-start configuration manager - uses scheduled tasks"""
    TASK_NAME = "SmartClipboardAutostart"

    def __init__(self):
        pass

    @staticmethod
    def get_current_exe_path():
        """Get current executable path"""
        if getattr(sys, 'frozen', False):
            return sys.executable
        else:
            return os.path.abspath(sys.argv[0])

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def run_as_admin_and_exit(self):
        if not self.is_admin():
            try:
                script = os.path.abspath(sys.argv[0])
                params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, f'"{script}"', params, 1
                )
                sys.exit(0)
            except Exception:
                sys.exit(1)

    def get_scheduled_task_exe_path(self):
        """Get exe path from scheduled task, returns None if task doesn't exist"""
        try:
            result = subprocess.run(
                ['schtasks', '/query', '/tn', self.TASK_NAME, '/fo', 'LIST', '/v'],
                capture_output=True,
                encoding='gbk',
                errors='ignore'
            )
            if result.returncode != 0:
                return None

            # Parse "Task To Run" field
            for line in result.stdout.split('\n'):
                if 'Task To Run' in line or '要运行的任务' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        exe_path = parts[1].strip()
                        exe_path = exe_path.strip('"')
                        return exe_path
            return None
        except Exception:
            return None

    def is_task_path_valid(self):
        """Check if scheduled task exists and path matches current exe"""
        task_exe_path = self.get_scheduled_task_exe_path()
        if task_exe_path is None:
            return False

        current_exe_path = self.get_current_exe_path()
        return os.path.normcase(task_exe_path) == os.path.normcase(current_exe_path)

    def delete_scheduled_task(self):
        """Delete scheduled task"""
        try:
            subprocess.run(
                ['schtasks', '/delete', '/tn', self.TASK_NAME, '/f'],
                capture_output=True,
                encoding='gbk',
                errors='ignore'
            )
        except Exception:
            pass

    def create_scheduled_task(self):
        """Create scheduled task, delete first if exists"""
        if not self.is_admin():
            return False

        app_exe_path = self.get_current_exe_path()
        if not os.path.exists(app_exe_path):
            return False

        current_user = os.getlogin()

        # Delete old task if exists
        self.delete_scheduled_task()

        command = [
            'schtasks', '/create', '/tn', self.TASK_NAME, '/tr', f'"{app_exe_path}"',
            '/sc', 'ONLOGON', '/ru', current_user, '/rl', 'HIGHEST', '/it', '/f'
        ]

        try:
            subprocess.run(command, capture_output=True, text=True, encoding='gbk', check=True)
            logging.info(f"AutoConfigManager: Created scheduled task pointing to {app_exe_path}")
            return True
        except Exception as e:
            logging.error(f"AutoConfigManager: Failed to create scheduled task: {e}")
            return False

    def setup_auto_start(self):
        """Setup auto-start: recreate task if doesn't exist or path mismatch"""
        if self.is_task_path_valid():
            logging.debug("AutoConfigManager: Scheduled task exists and path is valid.")
            return True

        self.run_as_admin_and_exit()
        return self.create_scheduled_task()
