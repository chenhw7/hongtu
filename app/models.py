from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, comment='用户名')
    password_hash = db.Column(db.String(256), comment='密码哈希')
    display_name = db.Column(db.String(64), comment='显示名称')
    role = db.Column(db.String(20), default='user', comment='角色：admin/user')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), nullable=False, comment='公司名称')
    contact_person = db.Column(db.String(50), comment='联系人')
    phone = db.Column(db.String(50), comment='电话')
    address = db.Column(db.String(500), comment='地址')
    industry_type = db.Column(db.String(50), comment='行业类型：市政/建筑/装饰/水务/电力/通信')
    source = db.Column(db.String(50), default='手动录入', comment='客户来源：爬虫采集/手动录入/Excel导入/转介绍/其他')
    status = db.Column(db.String(20), default='新线索', comment='状态：新线索/跟进中/已报价/已成交/已流失')
    notes = db.Column(db.Text, comment='备注')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    follow_ups = db.relationship('FollowUp', backref='customer', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Customer {self.company_name}>'


class FollowUp(db.Model):
    __tablename__ = 'follow_ups'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, comment='客户ID')
    content = db.Column(db.Text, nullable=False, comment='跟进内容')
    follow_type = db.Column(db.String(20), default='电话', comment='跟进方式：电话/拜访/微信/邮件')
    next_action = db.Column(db.String(200), comment='下一步行动')
    next_date = db.Column(db.Date, comment='下次跟进日期')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<FollowUp {self.customer_id} {self.follow_type}>'


class Lead(db.Model):
    __tablename__ = 'leads'
    id = db.Column(db.Integer, primary_key=True)
    bidding_number = db.Column(db.String(100), unique=True, comment='招标编号（唯一）')
    project_name = db.Column(db.String(500), comment='项目名称')
    announcement_type = db.Column(db.String(50), comment='公告类型：公开招标/中标公告/成交公告/更正公告/终止公告/竞争性磋商/其他公告等')
    buyer_name = db.Column(db.String(200), comment='采购单位')
    buyer_address = db.Column(db.String(300), comment='采购单位地址')
    region = db.Column(db.String(50), comment='地域（省级行政区）')
    contact_person = db.Column(db.String(50), comment='联系人')
    phone = db.Column(db.String(50), comment='电话')
    agency_name = db.Column(db.String(200), comment='采购代理机构名称')
    agency_phone = db.Column(db.String(50), comment='采购代理机构电话')
    budget_amount = db.Column(db.Float, comment='预算金额')
    publish_date = db.Column(db.Date, comment='发布日期')
    publish_time = db.Column(db.String(10), comment='发布时间（HH:MM，精确到分钟）')
    deadline = db.Column(db.Date, comment='截止日期')
    source_url = db.Column(db.String(500), comment='来源URL')
    source_type = db.Column(db.String(50), comment='来源类型：ccgp/gdgpo/eia')
    raw_data = db.Column(db.Text, comment='原始数据JSON')
    html_snapshot_path = db.Column(db.String(500), comment='详情页HTML快照的本地相对路径')
    is_converted = db.Column(db.Boolean, default=False, comment='是否已转为客户')
    converted_customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True, comment='转换后的客户ID')
    deleted = db.Column(db.Boolean, default=False, comment='软删除标记')
    is_favorited = db.Column(db.Boolean, default=False, comment='是否收藏')
    created_at = db.Column(db.DateTime, default=datetime.now)

    attachments = db.relationship('Attachment', backref='lead', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Lead {self.bidding_number} {self.project_name}>'


class Attachment(db.Model):
    """线索详情页中的附件（招标文件、报价单等下载文件）"""
    __tablename__ = 'attachments'
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False, comment='所属线索ID')
    file_name = db.Column(db.String(300), comment='文件名')
    file_url = db.Column(db.String(1000), comment='原始下载链接')
    local_path = db.Column(db.String(500), comment='本地保存的相对路径')
    file_size = db.Column(db.Integer, comment='文件大小（字节）')
    download_status = db.Column(db.String(20), default='待下载', comment='状态：待下载/成功/失败')
    error_msg = db.Column(db.String(500), comment='下载失败原因')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<Attachment {self.file_name}>'


class ScrapeTask(db.Model):
    __tablename__ = 'scrape_tasks'
    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), comment='数据源类型：ccgp/gdgpo')
    status = db.Column(db.String(20), default='待运行', comment='状态：待运行/运行中/完成/失败')
    target_url = db.Column(db.String(500), comment='目标URL')
    result_count = db.Column(db.Integer, default=0, comment='采集数量')
    started_at = db.Column(db.DateTime, comment='开始时间')
    finished_at = db.Column(db.DateTime, comment='结束时间')
    error_msg = db.Column(db.Text, comment='错误信息')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<ScrapeTask {self.task_type} {self.status}>'
