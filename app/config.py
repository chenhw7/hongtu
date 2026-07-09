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
    # 详情页快照与附件下载
    SCRAPE_SAVE_SNAPSHOT = True  # 是否保存详情页HTML快照（防止公告被撤回/修改后无法追溯）
    SCRAPE_DOWNLOAD_ATTACHMENTS = True  # 是否下载详情页中的附件（招标文件/报价单等）
    SCRAPE_ATTACHMENT_MAX_SIZE = 20 * 1024 * 1024  # 单个附件最大下载大小（字节），超出则跳过
    SCRAPE_ATTACHMENT_MAX_COUNT = 10  # 单条线索最多下载附件数量
    SCRAPE_SNAPSHOT_DIR = 'snapshots'  # 快照保存目录（相对于 instance 目录）
    SCRAPE_ATTACHMENT_DIR = 'attachments'  # 附件保存目录（相对于 instance 目录）
    # 分页
    PER_PAGE = 20
    # 文件上传大小限制
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_DIR = os.environ.get('LOG_DIR', 'logs')
    LOG_RETENTION_DAYS = int(os.environ.get('LOG_RETENTION_DAYS', 14))
    SLOW_REQUEST_MS = int(os.environ.get('SLOW_REQUEST_MS', 1000))
