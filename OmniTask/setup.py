from setuptools import setup

APP = ['gui.py']
DATA_FILES = ['speedometer.png', 'Stress.png', 'OmniTask.icns']
OPTIONS = {
    'argv_emulation': True,
    'packages': [
        'PyQt6',
        'psutil',
        'AppKit',
        'Foundation',
        'ApplicationServices',  
        'objc',
    ],
    'includes': [
        'main',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtNetwork',
        'sip',
        'PyQt6.sip',
    ],
    'excludes': [
        'tkinter', 'numpy', 'matplotlib', 'scipy', 'PIL', 'pandas', 'IPython', 
        'jupyter', 'test', '_winapi', 'nt', 'winreg', 'platformdirs.windows', 
        'ctypes._endian', 'packaging._manylinux',
    ],
    'iconfile': 'OmniTask.icns',
    'plist': {
        'CFBundleName': 'OmniTask',
        'CFBundleDisplayName': 'OmniTask',
        'CFBundleIdentifier': 'com.vrtx.omnitask',
        'CFBundleVersion': '1.0.1',
        'CFBundleShortVersionString': '1.0.1',
        'NSHumanReadableCopyright': 'Copyright © 2026, VRTX',
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'NSSupportsAutomaticGraphicsSwitching': True,
        'NSAccessibilityUsageDescription': 'This app needs accessibility permissions to manage windows and system processes.',
    },
    'semi_standalone': False,
    'site_packages': True,
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
