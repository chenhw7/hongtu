import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hongtu-dev-secret-key-2026'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///hongtu.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 爬虫配置
    SCRAPE_DELAY_MIN = 3
    SCRAPE_DELAY_MAX = 5
    SCRAPE_MAX_RETRIES = 3
    SCRAPE_CHECK_ROBOTS = False  # ccgp/gdgpo 无可用 robots.txt，检查反而触发反爬
    SCRAPE_ANTI_SCRAPE_WAIT = 60  # 检测到反爬/请求失败后的等待时间（秒）
    SCRAPER_KEYWORDS = ['管道', 'PVC管', 'HDPE管', 'PPR管', '给排水', '市政管道', '塑料管']
    # 分页
    PER_PAGE = 20
    # 文件上传大小限制
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_DIR = os.environ.get('LOG_DIR', 'logs')
    LOG_RETENTION_DAYS = int(os.environ.get('LOG_RETENTION_DAYS', 14))
    SLOW_REQUEST_MS = int(os.environ.get('SLOW_REQUEST_MS', 1000))
