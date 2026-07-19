# -*- mode: python ; coding: utf-8 -*-
"""鸿图建材获客工具 - PyInstaller打包配置"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Playwright 完整打包
playwright_datas = collect_data_files('playwright')
playwright_imports = collect_submodules('playwright')

# 查找Playwright浏览器安装路径
def get_playwright_browsers_path():
    """获取Playwright浏览器安装路径"""
    # 默认路径：%LOCALAPPDATA%\ms-playwright
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    default_path = os.path.join(local_app_data, 'ms-playwright')
    if os.path.isdir(default_path):
        return default_path
    # 备选：%USERPROFILE%\AppData\Local\ms-playwright
    user_profile = os.environ.get('USERPROFILE', '')
    alt_path = os.path.join(user_profile, 'AppData', 'Local', 'ms-playwright')
    if os.path.isdir(alt_path):
        return alt_path
    return None

pw_browsers_path = get_playwright_browsers_path()
pw_browser_datas = []
if pw_browsers_path:
    # 将整个ms-playwright目录打包为 browsers/
    pw_browser_datas = [(pw_browsers_path, 'browsers')]

block_cipher = None

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
    ] + playwright_datas + pw_browser_datas,
    hiddenimports=[
        # 爬虫顶层模块
        'scraper.ccgp',
        'scraper.gdgpo',
        'scraper.eia',
        'scraper.ggzyjy',
        'scraper.epoint',
        'scraper.fdtz',
        'scraper.gdcic',
        'scraper.pipebiz',
        'scraper.bjx',
        'scraper.ggzyjy_js',
        'scraper.ggzyjy_sc',
        'scraper.ggzyjy_zj',
        'scraper.gzfcj',
        'scraper.qcc',
        'scraper.poi',
        # 爬虫子包的子模块
        'scraper.ccgp.search',
        'scraper.ccgp.detail',
        'scraper.ccgp.parser',
        'scraper.ccgp.channel',
        'scraper.ccgp.utils',
        'scraper.eia.utils',
        'scraper.eia.regions',
        'scraper.ggzyjy.search',
        'scraper.ggzyjy.detail',
        'scraper.ggzyjy.parser',
        'scraper.ggzyjy.utils',
        'scraper.epoint.search',
        'scraper.epoint.detail',
        'scraper.epoint.parser',
        'scraper.epoint.utils',
        'scraper.fdtz.api',
        'scraper.fdtz.parser',
        'scraper.fdtz.utils',
        'scraper.gdcic.api',
        'scraper.gdcic.parser',
        'scraper.gdcic.utils',
        'scraper.pipebiz.browser',
        'scraper.pipebiz.parser',
        'scraper.pipebiz.utils',
        'scraper.bjx.browser',
        'scraper.bjx.parser',
        'scraper.bjx.utils',
        'scraper.gzfcj.api',
        'scraper.gzfcj.parser',
        # Flask扩展
        'flask_login',
        'flask_sqlalchemy',
        'flask_migrate',
        'flask_wtf',
        'wtforms',
        # 服务器
        'waitress',
        'waitress.task',
        'waitress.channel',
        # 调度
        'apscheduler.schedulers.background',
        'apscheduler.triggers.cron',
        'apscheduler.triggers.interval',
        # 系统托盘
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        # 网络
        'httpx',
        'httpx._transports',
        'httpx._transports.default',
        # 解析
        'lxml',
        'lxml.html',
        'lxml.etree',
    ] + playwright_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'tkinter', 'PyQt5'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='hongtu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='hongtu.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='hongtu',
)
