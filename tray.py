import webbrowser

from PIL import Image, ImageDraw
import pystray


def create_icon_image():
    """创建一个简单的托盘图标（蓝色方块带白色H字母）"""
    img = Image.new('RGB', (64, 64), color=(41, 128, 185))
    draw = ImageDraw.Draw(img)
    # 画一个简单的H字母
    draw.text((22, 15), 'H', fill='white')
    return img


def run_tray(port):
    """运行系统托盘，阻塞主线程"""

    def open_browser(icon, item):
        webbrowser.open(f'http://localhost:{port}')

    def quit_app(icon, item):
        from scraper.scheduler import stop_scheduler
        stop_scheduler()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem('打开浏览器', open_browser, default=True),
        pystray.MenuItem('退出', quit_app),
    )

    icon = pystray.Icon(
        name='hongtu',
        icon=create_icon_image(),
        title='鸿图建材获客工具',
        menu=menu,
    )

    icon.run()
