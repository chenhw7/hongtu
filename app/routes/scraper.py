# -*- coding: utf-8 -*-
"""爬虫控制面板路由"""
import threading
from datetime import datetime, date

from flask import Blueprint, render_template, jsonify, request, current_app

from app.models import Customer, Lead, ScrapeTask
from app.extensions import db

scraper = Blueprint('scraper', __name__, url_prefix='/scraper')

# 全局运行中任务追踪 {task_type: thread}
_running_tasks = {}


def _run_scraper_task(app, task_type, keywords, max_pages):
    """在后台线程中执行爬虫采集

    Args:
        app: Flask 应用实例
        task_type: 数据源标识（如 'ccgp', 'gdgpo', 'eia', 'poi'）
        keywords: 关键词列表
        max_pages: 最大页数
    """
    with app.app_context():
        try:
            from scraper.registry import get_scraper_class
            ScraperClass = get_scraper_class(task_type)
            if ScraperClass is None:
                return
            scraper_instance = ScraperClass(app=app)
            scraper_instance.run(keywords=keywords, max_pages=max_pages)
        except Exception as e:
            current_app.logger.exception('爬虫后台任务异常 [%s]: %s', task_type, e)
        finally:
            # 清理运行标记
            _running_tasks.pop(task_type, None)


@scraper.route('/')
def index():
    """爬虫控制面板页面"""
    from scraper.registry import SCRAPER_REGISTRY, get_all_source_types

    # 统计信息
    total_leads = Lead.query.count()
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')
    today_leads = Lead.query.filter(
        db.func.date(Lead.created_at) == today_str
    ).count()
    converted_leads = Lead.query.filter_by(is_converted=True).count()

    # 各来源统计 — 循环 registry 自动生成
    source_stats = {}
    for source_type in get_all_source_types(lead_only=True):
        source_stats[f'{source_type}_count'] = Lead.query.filter_by(source_type=source_type).count()
        source_stats[f'last_{source_type}'] = ScrapeTask.query.filter_by(
            task_type=source_type
        ).order_by(ScrapeTask.created_at.desc()).first()

    # POI 统计特殊处理（产出 Customer 而非 Lead）
    poi_count = Customer.query.filter_by(source='地图POI采集').count()
    last_poi = ScrapeTask.query.filter_by(task_type='poi').order_by(
        ScrapeTask.created_at.desc()).first()

    # 最近10条采集任务
    recent_tasks = ScrapeTask.query.order_by(
        ScrapeTask.created_at.desc()
    ).limit(10).all()

    # 配置的关键词
    keywords = current_app.config.get('SCRAPER_KEYWORDS', [])
    # 各数据源官网地址（用于前端"官网"快捷跳转链接）
    source_sites = current_app.config.get('SCRAPER_SOURCE_SITES', {})
    from scraper.eia import REGIONS as EIA_REGIONS
    eia_all_keywords = ','.join(f'region:{k}' for k in EIA_REGIONS)

    # 关键词统计（用于前端 placeholder 展示）
    from scraper.keywords import CCGP_KEYWORDS_FINAL
    ccgp_keywords_count = len(CCGP_KEYWORDS_FINAL)

    # 向后兼容：保持旧变量名供模板使用（Task #2 会改为循环渲染）
    ccgp_count = source_stats.get('ccgp_count', 0)
    gdgpo_count = source_stats.get('gdgpo_count', 0)
    eia_count = source_stats.get('eia_count', 0)
    ggzyjy_count = source_stats.get('ggzyjy_count', 0)
    fdtz_count = source_stats.get('fdtz_count', 0)
    last_ccgp = source_stats.get('last_ccgp')
    last_gdgpo = source_stats.get('last_gdgpo')
    last_eia = source_stats.get('last_eia')
    last_ggzyjy = source_stats.get('last_ggzyjy')
    pipebiz_count = source_stats.get('pipebiz_count', 0)
    last_pipebiz = source_stats.get('last_pipebiz')
    last_fdtz = source_stats.get('last_fdtz')

    return render_template(
        'scraper/panel.html',
        total_leads=total_leads,
        today_leads=today_leads,
        converted_leads=converted_leads,
        ccgp_count=ccgp_count,
        gdgpo_count=gdgpo_count,
        eia_count=eia_count,
        ggzyjy_count=ggzyjy_count,
        pipebiz_count=pipebiz_count,
        fdtz_count=fdtz_count,
        poi_count=poi_count,
        last_ccgp=last_ccgp,
        last_gdgpo=last_gdgpo,
        last_eia=last_eia,
        last_ggzyjy=last_ggzyjy,
        last_pipebiz=last_pipebiz,
        last_fdtz=last_fdtz,
        last_poi=last_poi,
        recent_tasks=recent_tasks,
        keywords=keywords,
        ccgp_keywords_count=ccgp_keywords_count,
        source_sites=source_sites,
        eia_regions=EIA_REGIONS,
        eia_all_keywords=eia_all_keywords,
        running_tasks=dict(_running_tasks),
        source_stats=source_stats,
        registry=SCRAPER_REGISTRY,
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

    # 解析关键词：留空时传 None，交给各数据源自己的 run() 决定默认值
    # （ccgp/gdgpo 走 BaseScraper.run() 的 self.keywords，即 SCRAPER_KEYWORDS；
    # poi/eia 走各自重写的 run()，用 POI_KEYWORDS×POI_CITIES / region 列表，
    # 不能在这里统一塞 SCRAPER_KEYWORDS，否则会把管道招标关键词错当成
    # poi 的"关键词@城市"或 eia 的"region:xxx"伪关键词，导致全部判定为无效）
    if keywords_str:
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    else:
        keywords = None

    # 确定要运行的数据源（POI 产出的是 Customer 潜在客户而非 Lead 招投标线索，
    # 与 ccgp/gdgpo/eia 性质不同，'all' 不自动包含 poi，需单独触发）
    from scraper.registry import get_all_source_types

    task_types = []
    if task_type == 'all':
        task_types = get_all_source_types(include_in_all=True)
    elif task_type in get_all_source_types():
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


def _resolve_control_task_types(task_type):
    """将 task_type ('ccgp'/'gdgpo'/'all') 解析为当前正在运行的数据源列表。"""
    from scraper.registry import get_all_source_types
    if task_type == 'all':
        candidates = get_all_source_types(include_in_all=True)
    elif task_type in get_all_source_types():
        candidates = [task_type]
    else:
        return None
    return [tt for tt in candidates if tt in _running_tasks and _running_tasks[tt].is_alive()]


@scraper.route('/pause', methods=['POST'])
def pause():
    """暂停指定数据源的采集任务（仅暂停，不终止线程）"""
    from scraper import progress

    data = request.get_json(silent=True) or request.form
    task_type = data.get('task_type', 'ccgp')

    task_types = _resolve_control_task_types(task_type)
    if task_types is None:
        return jsonify({'success': False, 'message': f'无效的数据源: {task_type}'}), 400
    if not task_types:
        return jsonify({'success': False, 'message': '没有正在运行的采集任务'}), 409

    paused = [tt for tt in task_types if progress.request_pause(tt)]
    if not paused:
        return jsonify({'success': False, 'message': '暂停失败，任务可能已结束'}), 409

    return jsonify({'success': True, 'message': f'已暂停: {", ".join(paused)}', 'task_types': paused})


@scraper.route('/resume', methods=['POST'])
def resume():
    """恢复指定数据源已暂停的采集任务"""
    from scraper import progress

    data = request.get_json(silent=True) or request.form
    task_type = data.get('task_type', 'ccgp')

    task_types = _resolve_control_task_types(task_type)
    if task_types is None:
        return jsonify({'success': False, 'message': f'无效的数据源: {task_type}'}), 400
    if not task_types:
        return jsonify({'success': False, 'message': '没有正在运行的采集任务'}), 409

    resumed = [tt for tt in task_types if progress.request_resume(tt)]
    if not resumed:
        return jsonify({'success': False, 'message': '恢复失败，任务可能已结束'}), 409

    return jsonify({'success': True, 'message': f'已恢复: {", ".join(resumed)}', 'task_types': resumed})


@scraper.route('/stop', methods=['POST'])
def stop():
    """停止指定数据源的采集任务（采集线程会在当前页处理完后安全退出）"""
    from scraper import progress

    data = request.get_json(silent=True) or request.form
    task_type = data.get('task_type', 'ccgp')

    task_types = _resolve_control_task_types(task_type)
    if task_types is None:
        return jsonify({'success': False, 'message': f'无效的数据源: {task_type}'}), 400
    if not task_types:
        return jsonify({'success': False, 'message': '没有正在运行的采集任务'}), 409

    stopped = [tt for tt in task_types if progress.request_stop(tt)]
    if not stopped:
        return jsonify({'success': False, 'message': '停止失败，任务可能已结束'}), 409

    return jsonify({'success': True, 'message': f'正在停止: {", ".join(stopped)}', 'task_types': stopped})


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


@scraper.route('/progress')
def progress():
    """获取实时采集进度（AJAX）"""
    from scraper.progress import get_all_progress

    progress_data = get_all_progress()

    any_running = any(
        thread.is_alive() for thread in _running_tasks.values()
    )

    return jsonify({
        'success': True,
        'progress': progress_data,
        'any_running': any_running,
    })
