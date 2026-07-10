"""清除数据库数据（保留用户账号）并清理附件与快照文件。

用法: python clear_data.py
用于开发阶段快速重置数据，保留 users 表以便直接登录继续使用。
"""

import os
import shutil
import sys

# 确保 Windows 终端能正确输出中文
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app import create_app
from app.extensions import db
from app.models import Customer, FollowUp, Lead, Attachment, ScrapeTask


def clean_files(app):
    """清理 instance 下的 attachments 和 snapshots 目录。"""
    results = {}
    for dir_name in ('attachments', 'snapshots'):
        dir_path = os.path.join(app.instance_path, dir_name)
        count = 0
        if os.path.isdir(dir_path):
            try:
                count = sum(1 for _ in os.scandir(dir_path))
                shutil.rmtree(dir_path)
                os.makedirs(dir_path)
            except OSError as e:
                print(f'  ⚠ 清理 {dir_name} 目录失败: {e}')
                results[dir_name] = -1
                continue
        results[dir_name] = count
    return results


def clean_database():
    """清除业务数据表，保留 users 表。"""
    models = [
        (Attachment, '附件记录'),
        (FollowUp, '跟进记录'),
        (Lead, '线索'),
        (Customer, '客户'),
        (ScrapeTask, '爬虫任务'),
    ]

    results = {}
    for model, label in models:
        count = model.query.count()
        if count > 0:
            model.query.delete()
        results[label] = count

    db.session.commit()
    return results


def main():
    app = create_app()

    with app.app_context():
        # 统计当前数据量
        stats = {
            '客户': Customer.query.count(),
            '跟进记录': FollowUp.query.count(),
            '线索': Lead.query.count(),
            '附件记录': Attachment.query.count(),
            '爬虫任务': ScrapeTask.query.count(),
        }

        total = sum(stats.values())

        print('=' * 50)
        print('  鸿图建材 - 数据库清理工具')
        print('=' * 50)
        print()
        print('  即将清除以下数据：')
        print()
        for label, count in stats.items():
            print(f'    {label}: {count} 条')
        print()
        print(f'  共 {total} 条记录')
        print(f'  ✅ users 表将被保留')
        print(f'  ✅ instance/attachments/ 和 instance/snapshots/ 将被清空')
        print()

        if total == 0:
            print('  没有需要清除的数据。')
            return

        answer = input('  确认清除？(y/n): ').strip().lower()
        if answer != 'y':
            print('  已取消。')
            return

        print()
        print('  正在清理文件...')
        file_results = clean_files(app)
        for name, count in file_results.items():
            if count >= 0:
                print(f'    {name}: 已删除 {count} 个文件')

        print()
        print('  正在清除数据库...')
        db_results = clean_database()
        for label, count in db_results.items():
            print(f'    {label}: 已删除 {count} 条')

        print()
        print('  ✅ 清理完成。')


if __name__ == '__main__':
    main()