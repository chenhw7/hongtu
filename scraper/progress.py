# -*- coding: utf-8 -*-
"""爬虫实时进度追踪（线程安全的内存存储）

供后台爬虫线程写入进度、Web 路由读取进度，实现网页实时展示。
进度仅保存在内存中，不落库；每个数据源（task_type）一条进度记录。
"""
import threading
import time

# {task_type: {...progress fields...}}
_registry = {}
_lock = threading.Lock()

# 已结束的进度保留时长（秒），便于前端最后一次轮询读到终态
_FINISHED_TTL = 60

# {task_type: {'event': threading.Event, 'paused': bool, 'stop': bool}}
# event 语义：set = 运行中（不阻塞），clear = 已暂停（阻塞等待）
_controls = {}
_control_lock = threading.Lock()


def start_progress(task_type, task_id, total_keywords, max_pages):
    """初始化某数据源的进度记录。"""
    total_pages = max(int(total_keywords) * int(max_pages), 1)
    with _lock:
        _registry[task_type] = {
            'task_type': task_type,
            'task_id': task_id,
            'status': '运行中',
            'total_keywords': int(total_keywords),
            'max_pages': int(max_pages),
            'total_pages': total_pages,
            'done_pages': 0,
            'keyword_index': 0,
            'current_keyword': '',
            'current_page': 0,
            'collected': 0,
            'message': '准备开始采集...',
            'error_msg': None,
            'started_at': time.time(),
            'updated_at': time.time(),
            'finished_at': None,
        }


def update_progress(task_type, **fields):
    """更新进度字段。

    可更新键：keyword_index / current_keyword / current_page /
    done_pages / collected / message / status。
    """
    with _lock:
        entry = _registry.get(task_type)
        if entry is None:
            return
        for key, value in fields.items():
            if key in entry:
                entry[key] = value
        entry['updated_at'] = time.time()


def finish_progress(task_type, status, collected=0, error_msg=None):
    """标记某数据源采集结束（完成/失败/已停止）。"""
    with _lock:
        entry = _registry.get(task_type)
        if entry is None:
            return
        entry['status'] = status
        entry['collected'] = collected
        entry['error_msg'] = str(error_msg)[:500] if error_msg else None
        if status == '完成':
            entry['message'] = '采集完成'
        elif status == '已停止':
            entry['message'] = '采集已手动停止'
        else:
            entry['message'] = '采集失败'
        entry['finished_at'] = time.time()
        entry['updated_at'] = time.time()


def clear_progress(task_type):
    """清除某数据源的进度记录。"""
    with _lock:
        _registry.pop(task_type, None)


# ----------------------------------------------------------------------
# 暂停 / 继续 / 停止 控制
# ----------------------------------------------------------------------
def init_control(task_type):
    """初始化某数据源的暂停/停止控制状态（每次开始采集时调用）。"""
    with _control_lock:
        event = threading.Event()
        event.set()  # 默认：运行中，不阻塞
        _controls[task_type] = {'event': event, 'paused': False, 'stop': False}


def request_pause(task_type):
    """请求暂停某数据源的采集。返回 True 表示请求已生效。"""
    with _control_lock:
        ctrl = _controls.get(task_type)
        if ctrl is None or ctrl['stop']:
            return False
        ctrl['paused'] = True
        ctrl['event'].clear()
    update_progress(task_type, status='已暂停', message='采集已暂停，点击继续可恢复')
    return True


def request_resume(task_type):
    """请求恢复某数据源的采集。返回 True 表示请求已生效。"""
    with _control_lock:
        ctrl = _controls.get(task_type)
        if ctrl is None or ctrl['stop']:
            return False
        ctrl['paused'] = False
        ctrl['event'].set()
    update_progress(task_type, status='运行中', message='采集已恢复')
    return True


def request_stop(task_type):
    """请求停止某数据源的采集。返回 True 表示请求已生效。"""
    with _control_lock:
        ctrl = _controls.get(task_type)
        if ctrl is None:
            return False
        ctrl['stop'] = True
        ctrl['paused'] = False
        ctrl['event'].set()  # 解除可能的暂停阻塞，让采集线程尽快检测到停止请求
    update_progress(task_type, message='正在停止采集...')
    return True


def is_paused(task_type):
    """查询某数据源当前是否处于暂停状态。"""
    with _control_lock:
        ctrl = _controls.get(task_type)
        return bool(ctrl and ctrl['paused'])


def is_stop_requested(task_type):
    """查询某数据源是否已被请求停止。"""
    with _control_lock:
        ctrl = _controls.get(task_type)
        return bool(ctrl and ctrl['stop'])


def wait_if_paused(task_type):
    """若已被请求暂停，则阻塞在此，直到恢复或收到停止请求。"""
    with _control_lock:
        ctrl = _controls.get(task_type)
        event = ctrl['event'] if ctrl else None
    if event is not None:
        event.wait()


def clear_control(task_type):
    """清除某数据源的控制状态（采集结束时调用）。"""
    with _control_lock:
        _controls.pop(task_type, None)


def get_all_progress():
    """返回所有进度的快照（含计算出的 percent）。

    同时清理已结束且超过 TTL 的旧记录。
    """
    now = time.time()
    snapshot = {}
    with _lock:
        expired = []
        for task_type, entry in _registry.items():
            finished_at = entry.get('finished_at')
            if finished_at and (now - finished_at) > _FINISHED_TTL:
                expired.append(task_type)
                continue

            total_pages = entry.get('total_pages') or 1
            done_pages = entry.get('done_pages') or 0
            if entry.get('status') in ('完成', '失败'):
                percent = 100
            else:
                percent = int(min(done_pages / total_pages, 1.0) * 100)

            item = dict(entry)
            item['percent'] = percent
            item['paused'] = is_paused(task_type)
            # 不向前端暴露原始时间戳（float），改为运行秒数
            started_at = entry.get('started_at')
            end = finished_at or now
            item['elapsed'] = round(end - started_at, 1) if started_at else None
            item.pop('started_at', None)
            item.pop('updated_at', None)
            item.pop('finished_at', None)
            snapshot[task_type] = item

        for task_type in expired:
            _registry.pop(task_type, None)

    return snapshot
