# SmartClipboard 打包计划

## 项目概述

- **主文件**: `ai_studio_code.py`
- **图标**: `icon.png`
- **框架**: PySide6 (Qt6)
- **依赖**: html2text, pynput, pywin32
- **目标**: 打包为 Windows 单文件 exe

## 打包方案

使用 PyInstaller 打包为单文件 exe (`--onefile`)

## 关键配置

### 1. 隐藏导入 (Hidden Imports)

PyInstaller 无法自动检测以下动态导入的模块，需要显式声明：

```python
hiddenimports=[
    'PySide6.QtCore',
    'PySide6.QtGui', 
    'PySide6.QtWidgets',
    'html2text',
    'html2text.cli',
    'pynput.keyboard',
    'pynput.mouse',
    'win32gui',
    'win32con',
    'win32process',
    'win32api',
]
```

### 2. 数据文件包含

图标文件需要在打包时包含：

```python
a = Analysis(
    ['ai_studio_code.py'],
    datas=[('icon.png', '.')],
    ...
)
```

### 3. 运行时钩子

PySide6 需要运行时钩子来正确初始化 Qt 插件路径。

## 打包命令

已验证可用的打包命令（包含图标和数据文件）：

```powershell
pyinstaller --onefile --windowed --icon=icon.png --name=SmartClipboard `
    --hidden-import=html2text `
    --hidden-import=html2text.cli `
    --hidden-import=pynput.keyboard `
    --hidden-import=pynput.mouse `
    --hidden-import=win32gui `
    --hidden-import=win32con `
    --hidden-import=win32process `
    --hidden-import=win32api `
    --collect-all=PySide6 `
    --add-data "icon.png;." `
    ai_studio_code.py
```

**参数说明：**
- `--onefile`: 打包为单文件 exe
- `--windowed`: 无控制台窗口（GUI 应用）
- `--icon=icon.png`: 设置 exe 图标
- `--name=SmartClipboard`: 指定输出 exe 名称
- `--hidden-import`: 显式声明隐藏导入模块
- `--collect-all=PySide6`: 自动收集所有 PySide6 相关模块
- `--add-data "icon.png;."`: 将图标文件打包到 exe 中

## 替代方案：使用 spec 文件

对于更复杂的配置，建议使用 spec 文件：

```python
# build.spec
a = Analysis(
    ['ai_studio_code.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.')],
    hiddenimports=[
        'html2text',
        'html2text.cli',
        'pynput.keyboard',
        'pynput.mouse',
        'win32gui',
        'win32con',
        'win32process',
        'win32api',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SmartClipboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='icon.png',
)
```

执行：
```powershell
pyinstaller build.spec
```

## 注意事项

1. **单文件体积**: 单文件 exe 体积会比较大（预计 100MB+），因为包含所有运行时依赖
2. **首次启动**: 单文件首次启动时需要解压临时文件，启动时间较长
3. **杀毒软件**: 某些杀毒软件可能会对 PyInstaller 打包的文件报警
4. **Qt 插件**: 需要确保 Qt 平台插件正确包含

## 验证步骤

1. 运行打包命令
2. 检查 `dist/SmartClipboard.exe` 是否生成
3. 双击运行 exe，验证功能正常
4. 测试系统托盘图标
5. 测试剪贴板监控功能

## 潜在问题及解决方案

| 问题 | 解决方案 |
|------|----------|
| 找不到 icon.png | 使用 `--add-data` 参数包含图标 |
| Qt 平台错误 | 使用 `--collect-all PySide6` |
| pywin32 问题 | 显式添加 `hidden-import` |
| 启动黑屏 | 添加 `--windowed` 参数 |
