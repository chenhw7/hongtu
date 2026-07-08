# -*- coding: utf-8 -*-
"""Flask 扩展初始化"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'dashboard.index'
login_manager.login_message = '请先登录后再访问该页面'
