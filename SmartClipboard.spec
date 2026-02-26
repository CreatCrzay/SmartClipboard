# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs
import os
import site
import shutil

# Find PySide6 location
pyside6_path = None
for site_path in site.getsitepackages():
    candidate = os.path.join(site_path, 'PySide6')
    if os.path.exists(candidate):
        pyside6_path = candidate
        break

if not pyside6_path:
    pyside6_path = os.path.join(site.getusersitepackages(), 'PySide6')

datas = [('icon.png', '.')]
binaries = []

# Only include essential Qt libraries - exclude the huge ones
# Collect only essential PySide6 modules
essential_qt_modules = [
    'QtCore',
    'QtGui',
    'QtWidgets',
]

# Manually collect only necessary PySide6 files
pyside6_binaries = []
pyside6_datas = []

if pyside6_path:
    # Only include essential pyd files
    for mod in essential_qt_modules:
        mod_file = os.path.join(pyside6_path, f'{mod}.pyd')
        if os.path.exists(mod_file):
            pyside6_binaries.append((mod_file, 'PySide6'))

    # Include shiboken dependency
    shiboken_path = os.path.join(os.path.dirname(pyside6_path), 'shiboken6')
    if os.path.exists(shiboken_path):
        for f in os.listdir(shiboken_path):
            if f.endswith(('.pyd', '.dll')):
                pyside6_binaries.append((os.path.join(shiboken_path, f), 'shiboken6'))

    # Include only essential plugins
    essential_plugins = {
        'platforms': ['qwindows.dll', 'qminimal.dll'],
        'imageformats': ['qjpeg.dll', 'qpng.dll', 'qico.dll', 'qgif.dll', 'qwebp.dll'],
        'styles': ['qwindowsvistastyle.dll'],
        'iconengines': ['qsvgicon.dll'],
    }

    for plugin, files in essential_plugins.items():
        plugin_path = os.path.join(pyside6_path, 'plugins', plugin)
        if os.path.exists(plugin_path):
            for f in files:
                full_path = os.path.join(plugin_path, f)
                if os.path.exists(full_path):
                    pyside6_binaries.append((full_path, f'PySide6/plugins/{plugin}'))

    # Include MS Visual C++ runtime files from PySide6
    for f in ['MSVCP140.dll', 'MSVCP140_1.dll', 'MSVCP140_2.dll',
              'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll']:
        full_path = os.path.join(pyside6_path, f)
        if os.path.exists(full_path):
            pyside6_binaries.append((full_path, 'PySide6'))

    # Include pyside6 abi dll
    pyside6_abi = os.path.join(pyside6_path, 'pyside6.abi3.dll')
    if os.path.exists(pyside6_abi):
        pyside6_binaries.append((pyside6_abi, 'PySide6'))

binaries.extend(pyside6_binaries)
datas.extend(pyside6_datas)

hiddenimports = [
    'html2text',
    'html2text.cli',
    'pynput.keyboard',
    'pynput.mouse',
    'win32gui',
    'win32con',
    'win32process',
    'win32api',
    'PySide6.QtWidgets',
    'PySide6.QtCore',
    'PySide6.QtGui',
]

# Exclude all the large unnecessary modules
excludes = [
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DRender',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineQuick',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
    'PySide6.QtWebSockets',
    'PySide6.QtWebView',
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    'PySide6.QtGraphs',
    'PySide6.QtGraphsWidgets',
    'PySide6.QtLocation',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtQuick',
    'PySide6.QtQuick3D',
    'PySide6.QtQuickControls2',
    'PySide6.QtQuickTest',
    'PySide6.QtQuickWidgets',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',
    'PySide6.QtSensors',
    'PySide6.QtSerialBus',
    'PySide6.QtSerialPort',
    'PySide6.QtSpatialAudio',
    'PySide6.QtSql',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'PySide6.QtTest',
    'PySide6.QtTextToSpeech',
    'PySide6.QtUiTools',
    'PySide6.QtStateMachine',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtAxContainer',
    'PySide6.QtBluetooth',
    'PySide6.QtConcurrent',
    'PySide6.QtDBus',
    'PySide6.QtDesigner',
    'PySide6.QtHelp',
    'PySide6.QtHttpServer',
    'PySide6.QtNetworkAuth',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtPrintSupport',
    'PySide6.QtQml',
    'PySide6.QtNetwork',
    # numpy and other large packages if not needed
    'numpy',
    'pandas',
    'matplotlib',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=2,  # Increased optimization level
)

# Remove any binaries that match excluded patterns
filtered_binaries = []
for dest, src, typecode in a.binaries:
    skip = False
    # Check against excluded patterns
    for exclude in excludes:
        if exclude in dest or exclude in src:
            skip = True
            break
    # Skip unnecessary files by name
    if not skip:
        skip_files = ['opengl32sw.dll', 'Qt6OpenGL.dll', 'Qt6Network.dll',
                      'Qt6Pdf.dll', 'Qt6Qml.dll', 'Qt6Quick.dll',
                      'Qt6QmlModels.dll', 'Qt6QmlMeta.dll', 'Qt6QmlWorkerScript.dll',
                      'QtOpenGL.pyd', 'QtNetwork.pyd', 'QtSvg.pyd']
        for skip_file in skip_files:
            if skip_file.lower() in dest.lower():
                skip = True
                break
    if not skip:
        filtered_binaries.append((dest, src, typecode))
a.binaries = filtered_binaries

# Remove any datas that match excluded patterns
filtered_datas = []
for dest, src, typecode in a.datas:
    skip = False
    for exclude in excludes:
        if exclude in dest or exclude in src:
            skip = True
            break
    # Skip translations directory and other data files
    if not skip:
        if 'translations' in dest.lower() or 'translations' in src.lower():
            skip = True
    if not skip:
        filtered_datas.append((dest, src, typecode))
a.datas = filtered_datas

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SmartClipboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.png'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartClipboard',
)
