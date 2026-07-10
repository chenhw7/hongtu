import os
import shutil
from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from app.models import Customer, FollowUp, Lead, Attachment, ScrapeTask
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


@dashboard.route('/clear-data', methods=['POST'])
def clear_data():
    """清除数据库业务数据（保留 users 表）并清理附件与快照文件。"""
    password = request.form.get('password', '')

    if password != '1234':
        flash('密码错误，操作已取消。', 'error')
        return redirect(url_for('dashboard.index'))

    # 清理文件目录
    for dir_name in ('attachments', 'snapshots'):
        dir_path = os.path.join(current_app.instance_path, dir_name)
        if os.path.isdir(dir_path):
            try:
                shutil.rmtree(dir_path)
                os.makedirs(dir_path)
            except OSError:
                pass

    # 清除业务数据表（按外键依赖顺序：子表 → 父表）
    models = [
        (Attachment, '附件记录'),
        (FollowUp, '跟进记录'),
        (Lead, '线索'),
        (Customer, '客户'),
        (ScrapeTask, '爬虫任务'),
    ]

    total = 0
    for model, _ in models:
        count = model.query.count()
        if count > 0:
            model.query.delete()
        total += count

    db.session.commit()

    flash(f'数据清除完成，共删除 {total} 条记录。用户账号已保留。', 'success')
    return redirect(url_for('dashboard.index'))
