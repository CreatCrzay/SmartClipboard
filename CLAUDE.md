# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供关于此代码库的指导信息。

## 项目概述

SmartClipboard 是一款基于 Python 和 PySide6 开发的 Windows 桌面剪贴板管理工具。它替代/增强了原生的 Windows+V 剪贴板历史功能，当按下 Win+V 时会在光标位置显示一个自定义的浮动窗口。

## 架构设计

代码库采用分层架构，职责分离清晰：

### 入口点
- `main.py` - 应用程序入口。初始化 QApplication，检查自启动配置，并启动主窗口。

### 核心层 (`core/`)
- `windows_internals.py` - Windows 特定功能：
  - `HotkeyHookWorker`/`WinHotkeyListener`: 底层 Win32 键盘钩子 (WH_KEYBOARD_LL)，用于拦截 Win+V
  - `WindowHistoryManager`: 跟踪窗口焦点历史，在粘贴后恢复焦点
  - `AutoConfigManager`: 通过 Windows 计划任务管理自启动（创建任务需要管理员权限）
- `image_cache.py` - LRU 图像缓存，用于在剪贴板列表中渲染缩略图

### UI 层 (`ui/`)
- `main_app.py` - 主业务逻辑类，继承自 `MainWindowUI`。处理剪贴板监控、数据提取、粘贴操作和搜索功能
- `main_window.py` - 基础 UI 类，包含窗口设置、自定义滚动行为和拖拽移动功能
- `delegate.py` - `ClipboardDelegate`: 自定义 QStyledItemDelegate，用于在 QListView 中渲染剪贴板项目（文本/图像/文件）
- `widgets.py` - 自定义组件：`FloatingScrollBar`、`TitleBar`、`ClipboardCard`（旧版）
- `dialogs.py` - `SettingsDialog`: 无边框设置对话框，提供自动清理和历史记录限制选项
- `styles.py` - 集中管理的 QSS 样式表，用于所有 UI 组件

### 数据层
- `database.py` - `DatabaseManager`: SQLite 操作，支持剪贴板项目的置顶状态
- `models.py` - `ClipboardModel`: 用于 Qt 模型/视图架构的 QAbstractListModel
- `settings.py` - `SettingsManager`: 基于 JSON 的设置持久化

### 支持文件
- `constants.py` - UI 尺寸、颜色、字体大小
- `utils.py` - 工具函数：PyInstaller 的资源路径、文件元数据哈希
- `clean.py` - 清理脚本，用于删除 __pycache__、临时目录、.db 文件和构建产物

## 构建系统

项目使用 PyInstaller 创建可执行文件，使用 Inno Setup 打包安装程序。

### 开发命令

```bash
# 安装依赖
pip install pyside6 pynput pywin32 html2text

# 开发模式运行
python main.py

# 清理构建产物和缓存
python clean.py

# 构建可执行文件（清理后）
pyinstaller SmartClipboard.spec

# 创建安装程序（需要安装 Inno Setup 6）
# 在 Inno Setup 编译器中打开 installer.iss 并构建
# 或使用：iscc installer.iss
```

### 构建流程

1. **清理**：运行 `python clean.py` 删除旧的构建产物、缓存文件和数据库
2. **构建**：运行 `pyinstaller SmartClipboard.spec` - 输出到 `dist/SmartClipboard/`
3. **打包**：使用 Inno Setup 构建 `installer.iss` - 输出 `SmartClipboard_X.X_Setup.exe`

### 构建要点

- `.spec` 文件手动配置，排除不必要的 Qt 模块（WebEngine、Multimedia 等）以减小二进制体积
- `icon.png` 必须存在于项目根目录（被 spec 文件和代码引用）
- PyInstaller 仅收集必要的 PySide6 模块（QtCore、QtGui、QtWidgets）
- 应用程序在 `utils.resource_path()` 中使用 `sys._MEIPASS` 检测以实现 PyInstaller 兼容性

## 数据流

1. **剪贴板监控**：`SmartClipboardApp._on_clipboard_data_changed()` 监听 Qt 的 `dataChanged` 信号
2. **数据提取**：`_extract_clipboard_data()` 将内容规范化为三种类型：TEXT、IMAGE、FILES
3. **去重**：内容哈希与现有项目比较；重复项被移除
4. **存储**：通过 `DatabaseManager` 序列化到 SQLite
5. **显示**：`ClipboardModel` 通过 `QSortFilterProxyModel` 为搜索过滤提供数据给 `QListView`
6. **粘贴**：点击项目时，内容设置到剪贴板，窗口隐藏，然后通过 pynput 模拟 Ctrl+V

## Windows 集成

- **热键**：使用 `SetWindowsHookExW` 和 `WH_KEYBOARD_LL` 全局拦截 Win+V
- **自启动**：通过 `schtasks` 命令创建计划任务（登录时以最高权限运行）
- **窗口定位**：按下热键时窗口出现在光标位置
- **焦点恢复**：跟踪窗口历史，在粘贴后恢复先前应用程序的焦点

## 配置

设置存储在应用程序目录的 `settings.json` 中：
- `auto_clean_enabled` / `auto_clean_days`：自动删除旧的未置顶项目
- `max_history_enabled` / `max_history_count`：限制剪贴板历史记录总数
- `paste_as_file_enabled`：将图像粘贴为临时文件而非图像数据

## 数据库结构

SQLite 数据库 `smartclipboard.db`：
```sql
CREATE TABLE clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,        -- 'TEXT', 'IMAGE', 'FILES'
    content TEXT NOT NULL,     -- 序列化数据（文本、base64 图像或 JSON 文件路径）
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_pinned BOOLEAN DEFAULT FALSE
);
```

## 重要实现细节

- **图像存储**：图像使用 base64 编码的 PNG 格式存储在 SQLite 数据库中（而非文件路径）
- **文件存储**：文件存储原始路径为 JSON；文件不会被复制，仅引用
- **临时目录**：启动时在 `{app_dir}/temp/` 创建，退出时清理
- **搜索**：使用 `QSortFilterProxyModel` 在 `RoleContentPreview` 上进行过滤（不区分大小写）
- **粘贴模拟**：使用 `pynput.keyboard.Controller` 在设置剪贴板后发送 Ctrl+V
- **窗口行为**：无边框、置顶（`Qt.WindowStaysOnTopHint`）、半透明背景
