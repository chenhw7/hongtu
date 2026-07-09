# -*- coding: utf-8 -*-
"""接口请求日志

通过 Flask 请求钩子记录每个接口的调用情况：
- 请求开始：方法、路径、请求参数（query + body，敏感字段脱敏、超长截断）
- 请求结束：状态码、是否成功、耗时（毫秒）
- 慢请求告警、异常堆栈记录
"""
import time
import logging

from flask import g, request

logger = logging.getLogger('hongtu.access')

# 需要脱敏的参数键（不区分大小写）
_SENSITIVE_KEYS = {
    'password', 'passwd', 'pwd', 'token', 'secret',
    'authorization', 'access_token', 'refresh_token', 'api_key', 'apikey',
}

# 单个参数值最大长度，超出截断
_MAX_VALUE_LEN = 500
# 参数整体序列化最大长度
_MAX_PARAMS_LEN = 1000
# 静态资源等无需记录的路径前缀
_SKIP_PREFIXES = ('/static/',)


def _mask(key, value):
    """对敏感字段脱敏，并截断过长的值。"""
    if key.lower() in _SENSITIVE_KEYS:
        return '***'
    text = str(value)
    if len(text) > _MAX_VALUE_LEN:
        return text[:_MAX_VALUE_LEN] + '...(truncated)'
    return text


def _collect_params():
    """收集请求参数：query string + 表单/JSON body。"""
    params = {}

    # URL 查询参数
    for key in request.args:
        values = request.args.getlist(key)
        params[key] = _mask(key, values[0] if len(values) == 1 else values)

    # 表单参数
    if request.form:
        for key in request.form:
            values = request.form.getlist(key)
            params[key] = _mask(key, values[0] if len(values) == 1 else values)

    # JSON body
    if request.is_json:
        try:
            data = request.get_json(silent=True)
            if isinstance(data, dict):
                for key, value in data.items():
                    params[key] = _mask(key, value)
            elif data is not None:
                params['_json'] = _mask('_json', data)
        except Exception:
            pass

    if not params:
        return '{}'

    text = str(params)
    if len(text) > _MAX_PARAMS_LEN:
        text = text[:_MAX_PARAMS_LEN] + '...(truncated)'
    return text


def register_request_logging(app):
    """注册请求日志钩子。"""
    slow_ms = int(app.config.get('SLOW_REQUEST_MS', 1000))

    @app.before_request
    def _log_request_start():
        if request.path.startswith(_SKIP_PREFIXES):
            return
        g._req_start_time = time.perf_counter()
        logger.info(
            '请求开始 | %s %s | 来源=%s | 参数=%s',
            request.method, request.path, request.remote_addr, _collect_params(),
        )

    @app.after_request
    def _log_request_end(response):
        if request.path.startswith(_SKIP_PREFIXES):
            return response

        start = getattr(g, '_req_start_time', None)
        cost_ms = (time.perf_counter() - start) * 1000 if start else -1
        status = response.status_code
        success = '成功' if status < 400 else '失败'

        message = (
            '请求结束 | %s %s | 状态=%d | 结果=%s | 耗时=%.2fms'
        )
        args = (request.method, request.path, status, success, cost_ms)

        if status >= 500:
            logger.error(message, *args)
        elif status >= 400:
            logger.warning(message, *args)
        elif start is not None and cost_ms > slow_ms:
            logger.warning(message + ' | 慢请求', *args)
        else:
            logger.info(message, *args)

        return response

    @app.teardown_request
    def _log_request_exception(exc):
        if exc is not None:
            # 完整堆栈由 Flask 默认异常处理器记录，此处仅补充一条简洁的异常摘要，避免重复堆栈
            logger.error(
                '请求异常 | %s %s | %s: %s',
                request.method, request.path, type(exc).__name__, exc,
            )
