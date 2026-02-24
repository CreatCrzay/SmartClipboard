# SmartClipboard 项目架构文档

## 概述

SmartClipboard 采用模块化架构设计，将功能拆分到独立的模块中，便于维护和扩展。

---

## 项目结构

```
SmartClipboard/
├── main.py                      # 入口点 (25行)
├── constants.py                 # 常量定义 (48行)
├── utils.py                     # 通用工具函数 (40行)
├── settings.py                  # 设置管理 (54行)
├── database.py                  # 数据库管理 (233行)
├── models.py                    # 数据模型 (119行)
├── core/                        # 核心功能包
│   ├── __init__.py             # 包初始化
│   ├── image_cache.py          # 图片缓存
│   └── windows_internals.py    # 热键/窗口历史/自启动
├── ui/                          # UI组件包
│   ├── __init__.py             # 包初始化
│   ├── styles.py               # 样式函数
│   ├── delegate.py             # 列表项委托
│   ├── widgets.py              # 自定义控件
│   ├── dialogs.py              # 设置对话框
│   ├── main_window.py          # 主窗口UI
│   └── main_app.py             # 主应用逻辑
├── SmartClipboard.spec          # PyInstaller打包配置
├── icon.png                     # 应用图标
├── clean.py                     # 清理脚本
└── ARCHITECTURE.md              # 本文档
```

---

## 模块依赖关系

```
main.py (入口)
  └── ui/main_app.py (SmartClipboardApp - 主应用逻辑)
       ├── ui/main_window.py (MainWindowUI - 主窗口UI)
       │    ├── ui/widgets.py (TitleBar, FloatingScrollBar)
       │    └── ui/styles.py (样式函数)
       ├── ui/dialogs.py (SettingsDialog - 设置对话框)
       ├── ui/delegate.py (ClipboardDelegate - 列表渲染)
       ├── models.py (ClipboardModel - 数据模型)
       ├── database.py (DatabaseManager - 数据库)
       ├── settings.py (SettingsManager - 设置)
       ├── core/windows_internals.py (热键、窗口历史、自启动)
       ├── core/image_cache.py (图片缓存)
       └── utils.py, constants.py (工具函数和常量)
```

---

## 各模块职责

| 文件/目录 | 职责 | 代码量 |
|-----------|------|--------|
| `main.py` | 应用程序入口，初始化QApplication和主窗口 | ~25行 |
| `constants.py` | 颜色、尺寸、字体等常量定义 | ~48行 |
| `utils.py` | 通用工具函数：资源路径、应用数据路径、文件哈希 | ~40行 |
| `settings.py` | JSON设置文件读写管理 | ~54行 |
| `database.py` | SQLite数据库操作：增删改查、置顶、清理 | ~233行 |
| `models.py` | Qt数据模型：ClipboardModel，供QListView使用 | ~119行 |
| `core/image_cache.py` | 图片缓存管理，LRU策略 | ~67行 |
| `core/windows_internals.py` | Win+V热键监听、窗口历史、自启动任务 | ~405行 |
| `ui/styles.py` | 所有UI组件的样式表函数 | ~278行 |
| `ui/delegate.py` | 剪贴板项渲染委托（文本/图片/文件） | ~221行 |
| `ui/widgets.py` | 自定义控件：滚动条、标题栏、卡片 | ~482行 |
| `ui/dialogs.py` | 设置对话框UI | ~134行 |
| `ui/main_window.py` | 主窗口UI布局 | ~223行 |
| `ui/main_app.py` | 主应用逻辑：剪贴板监控、粘贴、搜索 | ~937行 |

---

## 启动流程

```
1. main.py
   ├── AutoConfigManager.setup_auto_start()  # 检查/创建自启动任务
   ├── QApplication 初始化
   ├── SmartClipboardApp 初始化
   │    ├── 设置管理器、数据库管理器初始化
   │    ├── 剪贴板信号连接
   │    ├── 模型和委托初始化
   │    ├── 托盘图标设置
   │    ├── 热键监听启动
   │    └── 启动清理检查
   └── app.exec() 进入事件循环
```

---

## 数据流

```
系统剪贴板变化
    ↓
_on_clipboard_data_changed()
    ↓
_extract_clipboard_data()  # 解析文本/图片/文件
    ↓
_process_new_system_clipboard_content()  # 去重、保存
    ↓
db_manager.add_clip()  # 写入数据库
    ↓
load_clips_from_db()  # 重新加载到模型
    ↓
model.set_data_list()  # 更新视图
```

---

## 后续开发指南

### 添加新功能

1. **修改UI**: 编辑 `ui/` 目录下的相应文件
2. **修改逻辑**: 编辑 `ui/main_app.py` 或 `core/` 目录
3. **修改数据库**: 编辑 `database.py`
4. **添加常量**: 编辑 `constants.py`

### 调试技巧

```python
# 在 main.py 中添加调试日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 运行程序查看详细日志
python main.py
```

---

## 文档版本

- **创建日期**: 2026-02-24
- **架构版本**: V4.6 模块化架构
- **状态**: ✅ 已完成
