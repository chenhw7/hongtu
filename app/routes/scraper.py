# -*- coding: utf-8 -*-
"""爬虫控制面板路由"""
import threading
from datetime import datetime, date

from flask import Blueprint, render_template, jsonify, request, current_app

from app.models import Lead, ScrapeTask
from app.extensions import db

scraper = Blueprint('scraper', __name__, url_prefix='/scraper')

# 全局运行中任务追踪 {task_type: thread}
_running_tasks = {}


def _run_scraper_task(app, task_type, keywords, max_pages):
    """在后台线程中执行爬虫采集

    Args:
        app: Flask 应用实例
        task_type: 'ccgp' 或 'gdgpo'
        keywords: 关键词列表
        max_pages: 最大页数
    """
    with app.app_context():
        try:
            if task_type == 'ccgp':
                from scraper.ccgp import CcgpScraper
                scraper_instance = CcgpScraper(app=app)
            elif task_type == 'gdgpo':
                from scraper.gdgpo import GdgpoScraper
                scraper_instance = GdgpoScraper(app=app)
            else:
                return

            scraper_instance.run(keywords=keywords, max_pages=max_pages)
        except Exception as e:
            current_app.logger.exception('爬虫后台任务异常 [%s]: %s', task_type, e)
        finally:
            # 清理运行标记
            _running_tasks.pop(task_type, None)


@scraper.route('/')
def index():
    """爬虫控制面板页面"""
    # 统计信息
    total_leads = Lead.query.count()
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')
    today_leads = Lead.query.filter(
        db.func.date(Lead.created_at) == today_str
    ).count()
    converted_leads = Lead.query.filter_by(is_converted=True).count()

    # 各来源数量
    ccgp_count = Lead.query.filter_by(source_type='ccgp').count()
    gdgpo_count = Lead.query.filter_by(source_type='gdgpo').count()

    # 最近10条采集任务
    recent_tasks = ScrapeTask.query.order_by(
        ScrapeTask.created_at.desc()
    ).limit(10).all()

    # 各数据源最后采集任务
    last_ccgp = ScrapeTask.query.filter_by(task_type='ccgp').order_by(
        ScrapeTask.created_at.desc()
    ).first()
    last_gdgpo = ScrapeTask.query.filter_by(task_type='gdgpo').order_by(
        ScrapeTask.created_at.desc()
    ).first()

    # 配置的关键词
    keywords = current_app.config.get('SCRAPER_KEYWORDS', [])

    return render_template(
        'scraper/panel.html',
        total_leads=total_leads,
        today_leads=today_leads,
        converted_leads=converted_leads,
        ccgp_count=ccgp_count,
        gdgpo_count=gdgpo_count,
        recent_tasks=recent_tasks,
        last_ccgp=last_ccgp,
        last_gdgpo=last_gdgpo,
        keywords=keywords,
        running_tasks=dict(_running_tasks),
    )


@scraper.route('/run', methods=['POST'])
def run():
    """手动触发爬虫采集

    POST 参数 (JSON 或 form):
        task_type: 'ccgp' / 'gdgpo' / 'all'
        keywords:  关键词列表（可选，默认用配置）
        max_pages: 最大页数（可选，默认5）
    """
    data = request.get_json(silent=True) or request.form
    task_type = data.get('task_type', 'ccgp')
    keywords_str = data.get('keywords', '')

    try:
        max_pages = int(data.get('max_pages', 5))
        if max_pages < 1 or max_pages > 50:
            return jsonify({'success': False, 'message': '页数范围: 1-50'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': '页数必须为整数'}), 400

    # 解析关键词
    if keywords_str:
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    else:
        keywords = current_app.config.get('SCRAPER_KEYWORDS', [])

    # 确定要运行的数据源
    task_types = []
    if task_type == 'all':
        task_types = ['ccgp', 'gdgpo']
    elif task_type in ('ccgp', 'gdgpo'):
        task_types = [task_type]
    else:
        return jsonify({'success': False, 'message': f'无效的数据源: {task_type}'}), 400

    # 检查是否已有任务在运行
    started = []
    for tt in task_types:
        if tt in _running_tasks and _running_tasks[tt].is_alive():
            return jsonify({
                'success': False,
                'message': f'{tt} 采集任务正在运行中，请等待完成',
            }), 409

    # 获取真实 Flask app（脱离 request context）
    app = current_app._get_current_object()

    for tt in task_types:
        thread = threading.Thread(
            target=_run_scraper_task,
            args=(app, tt, keywords, max_pages),
            daemon=True,
        )
        _running_tasks[tt] = thread
        thread.start()
        started.append(tt)

    return jsonify({
        'success': True,
        'message': f'已启动采集任务: {", ".join(started)}',
        'task_types': started,
    })


@scraper.route('/task/<int:task_id>')
def task_detail(task_id):
    """查看单个任务状态（AJAX返回JSON）"""
    task = db.session.get(ScrapeTask, task_id)
    if task is None:
        return jsonify({'success': False, 'message': '任务不存在'}), 404

    # 计算耗时
    duration = None
    if task.started_at and task.finished_at:
        duration = (task.finished_at - task.started_at).total_seconds()
    elif task.started_at and task.status == '运行中':
        duration = (datetime.now() - task.started_at).total_seconds()

    return jsonify({
        'success': True,
        'task': {
            'id': task.id,
            'task_type': task.task_type,
            'status': task.status,
            'result_count': task.result_count,
            'started_at': task.started_at.strftime('%Y-%m-%d %H:%M:%S') if task.started_at else None,
            'finished_at': task.finished_at.strftime('%Y-%m-%d %H:%M:%S') if task.finished_at else None,
            'duration': round(duration, 1) if duration else None,
            'error_msg': task.error_msg,
        }
    })


@scraper.route('/history')
def history():
    """任务历史列表（AJAX返回JSON）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    pagination = ScrapeTask.query.order_by(
        ScrapeTask.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    tasks = []
    for task in pagination.items:
        duration = None
        if task.started_at and task.finished_at:
            duration = (task.finished_at - task.started_at).total_seconds()

        tasks.append({
            'id': task.id,
            'task_type': task.task_type,
            'status': task.status,
            'result_count': task.result_count,
            'started_at': task.started_at.strftime('%Y-%m-%d %H:%M:%S') if task.started_at else None,
            'finished_at': task.finished_at.strftime('%Y-%m-%d %H:%M:%S') if task.finished_at else None,
            'duration': round(duration, 1) if duration else None,
            'error_msg': task.error_msg,
            'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S') if task.created_at else None,
        })

    return jsonify({
        'success': True,
        'tasks': tasks,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    })


@scraper.route('/status')
def status():
    """获取当前运行状态（AJAX）"""
    running = {}
    for tt, thread in _running_tasks.items():
        running[tt] = thread.is_alive()

    return jsonify({
        'success': True,
        'running': running,
    })
