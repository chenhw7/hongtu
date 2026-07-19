# -*- coding: utf-8 -*-
"""集中化日志配置

提供统一的日志格式、颜色控制台输出与按天轮转的文件输出。
- 控制台：按日志级别着色，便于开发排查
- 文件：logs/app.log 全量日志、logs/error.log 仅 ERROR 及以上
- 时间：精确到毫秒
仅依赖标准库。
"""
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler

# 统一日志格式与时间格式（精确到毫秒）
_LOG_FORMAT = '%(asctime)s | %(levelname)-5s | %(name)s:%(lineno)d | %(message)s'
_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# ANSI 颜色码（按级别）
_LEVEL_COLORS = {
    'DEBUG': '\033[37m',     # 灰白
    'INFO': '\033[32m',      # 绿
    'WARNING': '\033[33m',   # 黄
    'ERROR': '\033[31m',     # 红
    'CRITICAL': '\033[41m',  # 红底
}
_RESET = '\033[0m'


class MillisecondFormatter(logging.Formatter):
    """在 asctime 中输出精确到毫秒的时间戳。"""

    def formatTime(self, record, datefmt=None):
        # record.created 为浮点秒，msecs 为毫秒部分
        base = super().formatTime(record, datefmt or _DATE_FORMAT)
        return f'{base}.{int(record.msecs):03d}'


class ColoredFormatter(MillisecondFormatter):
    """控制台彩色 Formatter：仅对级别名着色。"""

    def format(self, record):
        color = _LEVEL_COLORS.get(record.levelname, '')
        # 复制级别名着色，避免污染 record 供其它 handler 复用
        original_levelname = record.levelname
        if color:
            record.levelname = f'{color}{original_levelname}{_RESET}'
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


def _enable_windows_ansi():
    """在 Windows 控制台启用 ANSI 转义支持（Win10+）。失败则静默忽略。"""
    if os.name != 'nt':
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004, STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _supports_color(stream):
    """判断输出流是否适合着色（tty 且非重定向）。"""
    return hasattr(stream, 'isatty') and stream.isatty()


def setup_logging(app):
    """为 Flask 应用配置统一日志。

    幂等：多次调用（如 debug 模式 reload）不会重复添加 handler。
    """
    log_level = str(app.config.get('LOG_LEVEL', 'INFO')).upper()
    log_dir = app.config.get('LOG_DIR', 'logs')
    retention = int(app.config.get('LOG_RETENTION_DAYS', 14))

    level = getattr(logging, log_level, logging.INFO)

    # 日志目录（相对项目根目录）
    if not os.path.isabs(log_dir):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base_dir, log_dir)
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()

    # 幂等：已配置过则跳过
    if getattr(root, '_hongtu_logging_configured', False):
        return

    root.setLevel(level)
    # 清理默认 handler，避免重复输出
    for handler in list(root.handlers):
        root.removeHandler(handler)

    plain_formatter = MillisecondFormatter(_LOG_FORMAT, _DATE_FORMAT)

    # 控制台 handler（着色）
    _enable_windows_ansi()
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    if _supports_color(sys.stdout):
        console.setFormatter(ColoredFormatter(_LOG_FORMAT, _DATE_FORMAT))
    else:
        console.setFormatter(plain_formatter)
    root.addHandler(console)

    # 全量文件 handler（按天轮转）
    app_file = TimedRotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        when='midnight', backupCount=retention, encoding='utf-8',
    )
    app_file.suffix = '%Y-%m-%d'
    app_file.setLevel(level)
    app_file.setFormatter(plain_formatter)
    root.addHandler(app_file)

    # 错误文件 handler（仅 ERROR 及以上）
    error_file = TimedRotatingFileHandler(
        os.path.join(log_dir, 'error.log'),
        when='midnight', backupCount=retention, encoding='utf-8',
    )
    error_file.suffix = '%Y-%m-%d'
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(plain_formatter)
    root.addHandler(error_file)

    # 让 Flask app.logger 与 werkzeug 走 root，避免自带 handler 重复输出
    for name in ('werkzeug', app.logger.name):
        target = logging.getLogger(name)
        target.handlers.clear()
        target.propagate = True
        target.setLevel(level)

    root._hongtu_logging_configured = True
    app.logger.setLevel(level)
