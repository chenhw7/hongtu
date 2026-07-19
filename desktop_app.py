import sys
import os

# PyInstaller frozen环境下的路径修正（必须在其他import之前）
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
    # Playwright浏览器路径：指向打包目录下的browsers文件夹
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(
        os.path.dirname(sys.executable), 'browsers'
    )

import socket
import webbrowser
import time
import threading
import logging

from app import create_app
from scraper.scheduler import stop_scheduler

logger = logging.getLogger(__name__)


def find_available_port(start=5000, attempts=10):
    """查找可用端口，如果start端口已被占用则尝试下一个"""
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start


def is_already_running(port=5000):
    """检测服务是否已经在运行"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def run_server(app, port):
    """在后台线程中运行waitress服务"""
    from waitress import serve
    serve(app, host='127.0.0.1', port=port)


def main():
    # 如果服务已在运行，直接打开浏览器
    if is_already_running(5000):
        logger.info('检测到服务已在运行，直接打开浏览器')
        webbrowser.open('http://localhost:5000')
        return

    app = create_app()
    port = find_available_port()
    logger.info(f'使用端口: {port}')

    # 后台线程启动服务
    server_thread = threading.Thread(target=run_server, args=(app, port), daemon=True)
    server_thread.start()

    # 等待服务启动
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{port}')
    logger.info('已打开浏览器')

    # 启动系统托盘（阻塞主线程）
    from tray import run_tray
    run_tray(port)


if __name__ == '__main__':
    main()
