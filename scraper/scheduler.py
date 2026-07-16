# -*- coding: utf-8 -*-
"""APScheduler 定时爬虫任务"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# 全局调度器实例
_scheduler = None


def run_daily_scrape(app):
    """每日自动采集任务

    在 Flask app context 中依次运行各数据源的爬虫。
    """
    from scraper.registry import SCRAPER_REGISTRY, get_scraper_class

    with app.app_context():
        logger.info('===== 每日定时采集开始 =====')

        for source_type, entry in SCRAPER_REGISTRY.items():
            if not entry.get('include_in_all'):
                continue  # 跳过 POI 等非 Lead 数据源
            try:
                ScraperClass = get_scraper_class(source_type)
                if ScraperClass is None:
                    logger.warning('无法加载采集器: %s', source_type)
                    continue
                scraper_instance = ScraperClass(app=app)
                count = scraper_instance.run()
                logger.info('%s 采集完成，新增 %d 条', source_type, count)
            except Exception as e:
                logger.exception('%s 定时采集失败: %s', source_type, e)

        logger.info('===== 每日定时采集结束 =====')


def init_scheduler(app):
    """初始化定时爬虫任务

    每天 08:00 自动执行采集。

    Args:
        app: Flask 应用实例

    Returns:
        BackgroundScheduler 实例
    """
    global _scheduler

    if _scheduler is not None:
        logger.warning('调度器已存在，跳过初始化')
        return _scheduler

    _scheduler = BackgroundScheduler()

    # 每天早上 8:00 执行采集
    _scheduler.add_job(
        func=run_daily_scrape,
        trigger='cron',
        hour=8,
        minute=0,
        args=[app],
        id='daily_scrape',
        name='每日政府采购信息采集',
        replace_existing=True,
    )

    _scheduler.start()
    logger.info('定时爬虫调度器已启动，每天 08:00 自动采集')

    return _scheduler


def stop_scheduler():
    """停止定时调度器"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info('定时爬虫调度器已停止')


def get_scheduler():
    """获取当前调度器实例"""
    return _scheduler
