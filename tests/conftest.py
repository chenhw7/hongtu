# -*- coding: utf-8 -*-
"""采集渠道真实网络烟雾测试共享基础设施。

提供：
- live_skip / playwright_skip / amap_key_skip / qcc_key_skip 跳过装饰器
- live_app fixture（内存 SQLite，隔离 instance/hongtu.db）
- assert_valid_leads 公共断言辅助函数
"""
import os

import pytest


# ── 跳过装饰器 ──

live_skip = pytest.mark.skipif(
    os.environ.get('LIVE_SMOKE_TESTS') != '1',
    reason='设置 LIVE_SMOKE_TESTS=1 才运行真实网络烟雾测试',
)

playwright_skip = pytest.mark.skipif(
    os.environ.get('LIVE_SMOKE_TESTS_PLAYWRIGHT') != '1',
    reason='设置 LIVE_SMOKE_TESTS_PLAYWRIGHT=1 才运行 Playwright 渠道测试',
)

amap_key_skip = pytest.mark.skipif(
    not os.environ.get('AMAP_API_KEY'),
    reason='未设置 AMAP_API_KEY 环境变量',
)

qcc_key_skip = pytest.mark.skipif(
    not os.environ.get('QCC_API_KEY'),
    reason='未设置 QCC_API_KEY 环境变量',
)


# ── 测试用 Flask 配置 ──

class _LiveTestConfig:
    """烟雾测试专用配置：内存 SQLite，关闭快照/附件/调度器。"""
    SECRET_KEY = 'live-test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SCRAPE_SAVE_SNAPSHOT = False
    SCRAPE_DOWNLOAD_ATTACHMENTS = False
    SCRAPE_DELAY_MIN = 0
    SCRAPE_DELAY_MAX = 0
    SCRAPE_MAX_RETRIES = 2
    SCRAPE_CHECK_ROBOTS = False
    SCRAPER_KEYWORDS = ['管道']
    LOG_LEVEL = 'WARNING'


@pytest.fixture
def live_app():
    """创建内存 SQLite 的 Flask app，用于需要 app context 的烟雾测试。

    不触发 scheduler，不入库 instance/hongtu.db。
    """
    from app import create_app
    from app.extensions import db as _db

    app = create_app(config_class=_LiveTestConfig)

    # 关闭 scheduler（create_app 会自动初始化，这里显式停止）
    from scraper.scheduler import stop_scheduler
    stop_scheduler()

    with app.app_context():
        _db.create_all()
        yield app


# ── 公共断言辅助 ──

def assert_valid_leads(leads, required_fields=None, source_type=''):
    """断言线索列表非空且关键字段非空。

    Args:
        leads: list[dict] 线索列表（_scrape_page 返回值）
        required_fields: 必须非空的字段名列表，默认 ['project_name', 'source_url']
        source_type: 数据源标识，用于错误消息
    """
    if required_fields is None:
        required_fields = ['project_name', 'source_url']
    assert leads is not None, f'[{source_type}] _scrape_page 返回 None（请求失败）'
    assert isinstance(leads, list), f'[{source_type}] 返回类型不是 list: {type(leads)}'
    assert len(leads) > 0, f'[{source_type}] 未抓取到任何线索'
    for i, lead in enumerate(leads[:3]):  # 只检查前 3 条，减少日志噪音
        for field in required_fields:
            value = lead.get(field, '')
            assert value, f'[{source_type}] 第{i+1}条线索 {field} 为空'
