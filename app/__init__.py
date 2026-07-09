import os
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine
from app.config import Config
from app.extensions import db, migrate, login_manager
from app.logging_config import setup_logging
from app.request_logging import register_request_logging


def create_app(config_class=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class or Config)

    # 初始化日志系统（尽早配置，便于后续初始化过程也能输出日志）
    setup_logging(app)

    # 确保instance目录存在
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # 注册蓝图
    from app.routes.dashboard import dashboard
    from app.routes.customers import customers
    from app.routes.leads import leads
    from app.routes.scraper import scraper
    app.register_blueprint(dashboard)
    app.register_blueprint(customers)
    app.register_blueprint(leads)
    app.register_blueprint(scraper)

    # 注册接口请求日志钩子
    register_request_logging(app)

    # SQLite WAL模式
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    # 注册 user_loader（Flask-Login）
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 创建数据库表
    with app.app_context():
        from app import models
        db.create_all()

    # 初始化定时调度器（debug 模式下避免重载重复启动）
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            from scraper.scheduler import init_scheduler
            init_scheduler(app)
        except Exception as e:
            app.logger.warning(f'调度器启动失败: {e}')

    return app
