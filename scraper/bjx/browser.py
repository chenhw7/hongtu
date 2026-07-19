# -*- coding: utf-8 -*-
"""bjx Playwright 浏览器操作封装。

北极星环保网（huanbao.bjx.com.cn / news.bjx.com.cn）子频道被 WAF 拦截，
返回 JS Challenge 页面。本模块使用 Playwright 渲染页面以通过 WAF 检查，
然后提取 Cookie 供 httpx 携带使用。

采集模式：Playwright 获取 Cookie → httpx + Cookie 请求列表页/详情页。
降级模式：全程使用 Playwright 渲染页面（当 Cookie + httpx 不稳定时）。
"""
import logging
import random
import time

logger = logging.getLogger(__name__)

# 环保频道首页（用于获取 WAF Cookie）
_ENV_CHANNEL_URL = 'https://huanbao.bjx.com.cn/'
# 招投标栏目首页（备选 Cookie 获取路径）
_ZB_CHANNEL_URL = 'https://news.bjx.com.cn/zb/'
# 主站首页（通常无 WAF，可用于验证连通性）
_MAIN_SITE_URL = 'https://www.bjx.com.cn/'

# Playwright 页面加载超时（毫秒）
_PAGE_TIMEOUT = 30000

# 反检测 JS：隐藏 headless 浏览器特征，绕过阿里云 WAF 检测
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
window.chrome = {runtime: {}};
"""


class BjxBrowser:
    """北极星环保网浏览器操作封装。

    管理 Playwright 浏览器生命周期，提供 Cookie 提取和页面加载方法。
    整个采集周期共享一个浏览器实例，避免反复启动。
    """

    def __init__(self, headless=True):
        self.headless = headless
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """启动浏览器并访问环保频道首页，等待 WAF JS Challenge 通过。

        Raises:
            ImportError: Playwright 未安装
            Exception: 浏览器启动失败
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                'Playwright 未安装。请执行: pip install playwright && playwright install chromium'
            )

        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ],
        )
        self.context = self.browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/126.0.0.0 Safari/537.36'
            ),
            locale='zh-CN',
            viewport={'width': 1280, 'height': 800},
        )
        # 注入反检测脚本（每个页面加载前执行）
        self.context.add_init_script(_STEALTH_JS)
        self.page = self.context.new_page()

        # 先访问主站（无 WAF），建立基础 Cookie
        logger.info('[bjx] 启动浏览器，访问主站...')
        try:
            self.page.goto(_MAIN_SITE_URL, wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)
            time.sleep(random.uniform(2, 3))
            logger.info('[bjx] 主站加载完成')
        except Exception as e:
            logger.warning('[bjx] 主站加载异常（继续尝试）: %s', e)

        # 再访问环保频道首页，等待 JS Challenge 完成
        logger.info('[bjx] 访问环保频道首页...')
        try:
            self.page.goto(_ENV_CHANNEL_URL, wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)
            self._wait_for_waf_resolve(timeout=20)
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
            logger.info('[bjx] 环保频道首页加载完成，WAF Challenge 已通过')
        except Exception as e:
            logger.warning('[bjx] 环保频道加载异常（继续尝试）: %s', e)

    def stop(self):
        """关闭浏览器并释放资源。"""
        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            logger.warning('[bjx] 浏览器关闭异常: %s', e)
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning('[bjx] Playwright 停止异常: %s', e)
        finally:
            self.browser = None
            self.context = None
            self.page = None
            self._playwright = None

    def extract_cookies(self):
        """从浏览器上下文中提取 Cookie 字符串。

        提取当前浏览器上下文中所有域的 Cookie，格式化为 httpx 可用的
        Cookie 字符串（"name1=val1; name2=val2"）。

        Returns:
            str: Cookie 字符串，失败返回空字符串
        """
        if not self.context:
            logger.error('[bjx] 浏览器上下文未初始化')
            return ''

        try:
            cookies = self.context.cookies()
            if not cookies:
                logger.warning('[bjx] 浏览器上下文中无 Cookie')
                return ''

            cookie_str = '; '.join(f'{c["name"]}={c["value"]}' for c in cookies)
            logger.info('[bjx] 提取到 %d 个 Cookie: %s',
                        len(cookies),
                        [c['name'] for c in cookies])
            return cookie_str
        except Exception as e:
            logger.warning('[bjx] Cookie 提取失败: %s', e)
            return ''

    def refresh_cookies(self):
        """重新访问环保频道刷新 Cookie。

        在 Cookie 过期或被 WAF 拦截时调用。

        Returns:
            str: 新的 Cookie 字符串，失败返回空字符串
        """
        if not self.page:
            logger.error('[bjx] 浏览器页面未初始化')
            return ''

        try:
            logger.info('[bjx] 刷新 WAF Cookie...')
            self.page.goto(_ENV_CHANNEL_URL, wait_until='networkidle', timeout=_PAGE_TIMEOUT)
            time.sleep(random.uniform(4, 6))
            return self.extract_cookies()
        except Exception as e:
            logger.warning('[bjx] Cookie 刷新失败: %s', e)
            return ''

    def load_page(self, url):
        """使用 Playwright 加载指定 URL 并返回 HTML。

        自动检测阿里云 WAF JS Challenge 并等待其通过（最多 15 秒）。

        Args:
            url: 页面 URL

        Returns:
            str: 页面 HTML，失败返回 None
        """
        if not self.page:
            logger.error('[bjx] 浏览器未启动')
            return None

        try:
            # 限速：每次页面操作前随机延迟
            delay = random.uniform(2, 4)
            time.sleep(delay)

            logger.info('[bjx] 加载页面: %s', url)
            self.page.goto(url, wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)

            # 等待 WAF JS Challenge 通过（阿里云 WAF 会自动执行 JS 并重定向）
            self._wait_for_waf_resolve()

            # 等待内容加载
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass

            time.sleep(random.uniform(1, 2))
            return self.page.content()
        except Exception as e:
            logger.warning('[bjx] 页面加载失败: %s - %s', url, e)
            return None

    def _wait_for_waf_resolve(self, timeout=15):
        """等待 WAF JS Challenge 通过，并尝试自动完成滑块验证。

        检测页面是否包含阿里云 WAF 特征（aliyun_waf_aa meta 标签），
        如果包含则：
        1. 先等待 JS Challenge 自动通过（部分场景无需交互）
        2. 若出现滑块验证码，尝试自动拖动完成

        Args:
            timeout: 最大等待秒数
        """
        try:
            content = self.page.content()
            if 'aliyun_waf_aa' not in content and 'aliyun_waf_bb' not in content:
                return  # 非 WAF 页面，无需等待

            logger.info('[bjx] 检测到 WAF Challenge，尝试通过...')

            # 第 1 步：等待 3 秒，看 JS Challenge 是否自动通过
            try:
                self.page.wait_for_function(
                    '() => !document.querySelector(\'meta[name="aliyun_waf_aa"]\')',
                    timeout=3000,
                )
                logger.info('[bjx] WAF JS Challenge 已自动通过')
                time.sleep(1)
                return
            except Exception:
                pass  # JS Challenge 未自动通过，尝试滑块

            # 第 2 步：尝试自动完成滑块验证
            if self._try_solve_slider():
                # 滑块完成后等待页面刷新
                try:
                    self.page.wait_for_function(
                        '() => !document.querySelector(\'meta[name="aliyun_waf_aa"]\')',
                        timeout=(timeout - 5) * 1000,
                    )
                    logger.info('[bjx] WAF 滑块验证已通过')
                    time.sleep(1)
                except Exception:
                    logger.debug('[bjx] 滑块后 WAF 仍未通过')
            else:
                logger.warning('[bjx] WAF 滑块验证未能自动完成，请在浏览器窗口中手动拖动滑块')
                # 给用户手动操作的时间
                try:
                    self.page.wait_for_function(
                        '() => !document.querySelector(\'meta[name="aliyun_waf_aa"]\')',
                        timeout=(timeout - 5) * 1000,
                    )
                    logger.info('[bjx] WAF 验证已通过（手动）')
                    time.sleep(1)
                except Exception:
                    logger.debug('[bjx] WAF 等待超时，继续')
        except Exception:
            logger.debug('[bjx] WAF 处理异常，继续')

    def _try_solve_slider(self):
        """尝试自动完成阿里云 WAF 滑块验证。

        查找滑块按钮并模拟人工拖动（加速→减速 + 随机偏移）。

        Returns:
            bool: True 表示找到并尝试了拖动，False 表示未找到滑块
        """
        import math

        # 常见阿里云 WAF 滑块选择器
        slider_selectors = [
            '#aliyunCaptcha-sliding-slider',
            '#nc_1_n1z',
            '.nc-lang-cnt .btn_slide',
            '.nc_wrapper .nc_scale .scale_text',
            '#nc_1__scale_text',
        ]

        slider = None
        for sel in slider_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    slider = el
                    logger.info('[bjx] 找到滑块元素: %s', sel)
                    break
            except Exception:
                continue

        if not slider:
            return False

        try:
            # 获取滑块和轨道的位置信息
            box = slider.bounding_box()
            if not box:
                return False

            # 轨道宽度（从滑块起始位置到右侧边界）
            # 尝试获取轨道元素宽度
            track_width = 340  # 默认值
            track_selectors = [
                '#aliyunCaptcha-sliding-body',
                '#nc_1_wrapper',
                '.nc-lang-cnt',
                '.nc_wrapper',
            ]
            for tsel in track_selectors:
                try:
                    track = self.page.query_selector(tsel)
                    if track:
                        tbox = track.bounding_box()
                        if tbox:
                            track_width = int(tbox['width']) - int(box['width']) - 10
                            break
                except Exception:
                    continue

            # 滑块中心坐标
            sx = box['x'] + box['width'] / 2
            sy = box['y'] + box['height'] / 2

            logger.info('[bjx] 开始拖动滑块，轨道宽度: %dpx', track_width)

            # 模拟人工拖动：先加速后减速 + 随机 Y 轴抨动
            self.page.mouse.move(sx, sy)
            time.sleep(random.uniform(0.1, 0.3))
            self.page.mouse.down()
            time.sleep(random.uniform(0.05, 0.15))

            # 分多步拖动，模拟人类轨迹
            total_steps = random.randint(25, 40)
            for i in range(1, total_steps + 1):
                # ease-out 曲线：开始快、结束慢
                progress = 1 - math.pow(1 - i / total_steps, 2)
                dx = track_width * progress
                # Y 轴随机抨动（模拟人手不稳）
                dy = random.uniform(-2, 2)
                self.page.mouse.move(sx + dx, sy + dy)
                time.sleep(random.uniform(0.005, 0.02))

            # 最终微调（模拟人类对齐）
            self.page.mouse.move(sx + track_width, sy + random.uniform(-1, 1))
            time.sleep(random.uniform(0.05, 0.1))
            self.page.mouse.up()

            time.sleep(2)  # 等待服务器验证
            return True

        except Exception as e:
            logger.debug('[bjx] 滑块拖动失败: %s', e)
            return False

    def search_keyword(self, keyword, page_num=1, stop_check=None):
        """搜索关键词并返回结果列表的 HTML。

        尝试以下路径（按优先级）：
        1. 环保频道搜索 URL
        2. 招投标栏目搜索 URL
        3. 降级到栏目 URL（仅第 1 页）

        Args:
            keyword: 搜索关键词
            page_num: 页码（从 1 开始）
            stop_check: 可选回调，每次 URL 尝试前调用（用于检查停止标志）

        Returns:
            str: 结果列表页 HTML，失败返回 None
        """
        if not self.page:
            logger.error('[bjx] 浏览器未启动')
            return None

        # 策略 1：环保频道搜索 URL
        search_urls = [
            f'https://huanbao.bjx.com.cn/news/list.html?kw={keyword}&page={page_num}',
            f'https://huanbao.bjx.com.cn/zhaobiao/list.html?kw={keyword}&page={page_num}',
            f'https://news.bjx.com.cn/zb/list.html?kw={keyword}&page={page_num}',
        ]

        for url in search_urls:
            if stop_check:
                stop_check()
            html = self.load_page(url)
            if html and self._has_search_results(html):
                logger.info('[bjx] 搜索成功: %s', keyword)
                return html

        # 策略 2：降级到栏目 URL（仅第 1 页）
        if page_num == 1:
            fallback_urls = [
                _ENV_CHANNEL_URL,
                _ZB_CHANNEL_URL,
            ]
            for url in fallback_urls:
                if stop_check:
                    stop_check()
                html = self.load_page(url)
                if html and self._has_search_results(html):
                    logger.info('[bjx] 栏目降级成功: %s', url)
                    return html

        logger.warning('[bjx] 搜索无结果: keyword=%s, page=%d', keyword, page_num)
        return None

    @staticmethod
    def _has_search_results(html):
        """检查 HTML 是否包含搜索结果（非空页面/错误页面）。"""
        if not html:
            return False

        import re
        # 检查是否有常见的列表元素
        li_count = len(re.findall(r'<li[^>]*>', html, re.I))
        if li_count >= 3:
            return True

        # 检查是否有日期模式（YYYY-MM-DD）
        date_count = len(re.findall(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', html))
        if date_count >= 2:
            return True

        return False
