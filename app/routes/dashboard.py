from datetime import date

from flask import Blueprint, render_template
from sqlalchemy import func

from app.models import Customer, FollowUp
from app.extensions import db

dashboard = Blueprint('dashboard', __name__)


@dashboard.route('/')
def index():
    """仪表盘：统计卡片 + 最近跟进 + 最近新增客户"""
    today = date.today()

    # 统计数据
    total_customers = Customer.query.count()
    today_new = Customer.query.filter(func.date(Customer.created_at) == today).count()
    # 待跟进客户数：有 FollowUp 的 next_date <= 今天（去重客户）
    pending_followups = db.session.query(
        func.count(func.distinct(FollowUp.customer_id))
    ).filter(FollowUp.next_date <= today).scalar() or 0

    # 最近5条跟进记录
    recent_followups = (
        FollowUp.query
        .order_by(FollowUp.created_at.desc())
        .limit(5)
        .all()
    )

    # 最近5条新增客户
    recent_customers = (
        Customer.query
        .order_by(Customer.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        'dashboard.html',
        total_customers=total_customers,
        today_new=today_new,
        pending_followups=pending_followups,
        recent_followups=recent_followups,
        recent_customers=recent_customers,
    )
