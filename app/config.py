import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hongtu-dev-secret-key-2026'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///hongtu.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 爬虫配置
    SCRAPE_DELAY_MIN = 3
    SCRAPE_DELAY_MAX = 5
    # EIA环评公示混合静态页面和公开接口，保持低并发、逐请求限速
    EIA_DELAY_MIN = 1
    EIA_DELAY_MAX = 2
    EIA_ANTI_SCRAPE_WAIT = 0  # 接口/schema 失败直接记录，不按通用反爬策略额外等待
    # 东莞列表第4页起需要验证码，日常用最近2天窗口并在采集器内按日期/受理号分片
    EIA_DONGGUAN_LOOKBACK_DAYS = 2
    # 肇庆首次全量采集（DB 无历史 lead 时不设日期过滤），后续走增量窗口
    EIA_ZHAOQING_LOOKBACK_DAYS = 3
    SCRAPE_MAX_RETRIES = 3
    SCRAPE_CHECK_ROBOTS = False  # ccgp/gdgpo 无可用 robots.txt，检查反而触发反爬
    SCRAPE_ANTI_SCRAPE_WAIT = 60  # 检测到反爬/请求失败后的等待时间（秒）
    # 默认搜索关键词（各采集器优先使用 scraper/keywords.py 中的分类关键词，
    # 此配置仅作为 BaseScraper.run() 未收到 keywords 参数时的兜底默认值）
    SCRAPER_KEYWORDS = ['管道', 'PVC管', 'HDPE管', 'PPR管', '给排水', '市政管道', '塑料管']
    # 各数据源官网地址（用于前端面板"官网"快捷跳转链接，新增数据源时在此追加即可）
    SCRAPER_SOURCE_SITES = {
        'ccgp': 'http://www.ccgp.gov.cn/',
        'gdgpo': 'https://gdgpo.czt.gd.gov.cn/',
        'poi': 'https://lbs.amap.com/',
    }
    # 高德地图 Web服务API Key（个人开发者免费申请：https://lbs.amap.com/ -> 控制台 ->
    # 创建应用 -> 添加Key -> 服务平台选"Web服务"，不要选"Web端(JS API)"）。
    # 不要把真实Key写进代码仓库，通过环境变量注入。
    AMAP_API_KEY = os.environ.get('AMAP_API_KEY', '')
    # 地图POI采集关键词（管道经销商/门店/工厂类目搜索词）
    POI_KEYWORDS = ['PVC管材', '给排水管件', '塑料管材经销', 'HDPE管材', 'PPR管材', '管材批发', '管件加工厂']
    # 地图POI采集城市范围（默认广东省21个地级市，与现有gdgpo数据源范围保持一致）
    POI_CITIES = [
        '广州', '深圳', '珠海', '汕头', '佛山', '韶关', '河源', '梅州', '惠州',
        '汕尾', '东莞', '中山', '江门', '阳江', '湛江', '茂名', '肇庆', '清远',
        '潮州', '揭阳', '云浮',
    ]
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
