# -*- coding: utf-8 -*-
"""线索管理路由"""
import json
from datetime import datetime, date
from io import BytesIO

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.extensions import db
from app.models import Lead, Customer
from app.config import Config

leads = Blueprint('leads', __name__, url_prefix='/leads')


def _apply_filters(query):
    """公共方法：对查询对象应用筛选条件"""
    source_type = request.args.get('source_type', '', type=str)
    is_converted = request.args.get('is_converted', '', type=str)
    q = request.args.get('q', '', type=str).strip()
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)

    if source_type:
        query = query.filter(Lead.source_type == source_type)

    if is_converted == '0':
        query = query.filter(Lead.is_converted == False)  # noqa: E712
    elif is_converted == '1':
        query = query.filter(Lead.is_converted == True)  # noqa: E712

    if q:
        keyword = f'%{q}%'
        query = query.filter(
            db.or_(
                Lead.project_name.like(keyword),
                Lead.buyer_name.like(keyword),
                Lead.contact_person.like(keyword),
            )
        )

    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Lead.publish_date >= d_from)
        except ValueError:
            pass

    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Lead.publish_date <= d_to)
        except ValueError:
            pass

    return query


@leads.route('/')
def index():
    """线索列表 - 支持筛选、搜索、分页"""
    page = request.args.get('page', 1, type=int)
    source_type = request.args.get('source_type', '', type=str)
    is_converted = request.args.get('is_converted', '', type=str)
    q = request.args.get('q', '', type=str).strip()
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)

    query = _apply_filters(Lead.query)
    query = query.order_by(Lead.publish_date.desc().nullslast(), Lead.created_at.desc())

    pagination = query.paginate(page=page, per_page=Config.PER_PAGE, error_out=False)

    # 构建查询参数用于分页链接
    query_args = {}
    if source_type:
        query_args['source_type'] = source_type
    if is_converted:
        query_args['is_converted'] = is_converted
    if q:
        query_args['q'] = q
    if date_from:
        query_args['date_from'] = date_from
    if date_to:
        query_args['date_to'] = date_to

    return render_template('leads/list.html',
                           leads=pagination,
                           source_type=source_type,
                           is_converted=is_converted,
                           q=q,
                           date_from=date_from,
                           date_to=date_to,
                           query_args=query_args,
                           today=date.today())


@leads.route('/<int:id>')
def detail(id):
    """线索详情页"""
    lead = Lead.query.get_or_404(id)

    # 格式化原始数据JSON
    raw_data_json = ''
    if lead.raw_data:
        try:
            parsed = json.loads(lead.raw_data)
            raw_data_json = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            raw_data_json = lead.raw_data

    return render_template('leads/detail.html',
                           lead=lead,
                           raw_data_json=raw_data_json,
                           today=date.today())


@leads.route('/<int:id>/convert', methods=['POST'])
def convert(id):
    """一键转客户 - 将线索转为Customer记录"""
    lead = Lead.query.get_or_404(id)

    if lead.is_converted:
        flash('该线索已转化，无需重复操作', 'warning')
        return redirect(url_for('leads.detail', id=id))

    try:
        customer = Customer(
            company_name=lead.buyer_name or '未知单位',
            contact_person=lead.contact_person or '',
            phone=lead.phone or '',
            source='爬虫采集',
            status='新线索',
            notes=(f'由线索#{lead.id}自动转化\n'
                   f'项目名称：{lead.project_name or ""}\n'
                   f'招标编号：{lead.bidding_number or ""}'),
        )
        db.session.add(customer)
        db.session.flush()  # 获取 customer.id

        lead.is_converted = True
        lead.converted_customer_id = customer.id

        db.session.commit()
        flash(f'成功转化为客户：{customer.company_name}', 'success')
        return redirect(url_for('customers.detail', id=customer.id))
    except Exception:
        db.session.rollback()
        flash('转化失败，请重试或联系管理员', 'danger')
        return redirect(url_for('leads.detail', id=id))


@leads.route('/batch_convert', methods=['POST'])
def batch_convert():
    """批量转客户"""
    lead_ids = request.form.getlist('lead_ids')

    if not lead_ids:
        flash('请先选择要转化的线索', 'warning')
        return redirect(url_for('leads.index'))

    success_count = 0
    skip_count = 0

    for lid in lead_ids:
        try:
            lead = Lead.query.get(int(lid))
            if not lead or lead.is_converted:
                skip_count += 1
                continue

            customer = Customer(
                company_name=lead.buyer_name or '未知单位',
                contact_person=lead.contact_person or '',
                phone=lead.phone or '',
                source='爬虫采集',
                status='新线索',
                notes=(f'由线索#{lead.id}批量转化\n'
                       f'项目名称：{lead.project_name or ""}\n'
                       f'招标编号：{lead.bidding_number or ""}'),
            )
            db.session.add(customer)
            db.session.flush()

            lead.is_converted = True
            lead.converted_customer_id = customer.id
            success_count += 1
        except Exception:
            db.session.rollback()
            skip_count += 1
            continue

    try:
        db.session.commit()
        if success_count:
            flash(f'成功转化 {success_count} 条线索为客户', 'success')
        if skip_count:
            flash(f'{skip_count} 条线索已跳过（已转化或不存在）', 'info')
    except Exception:
        db.session.rollback()
        flash('批量转化失败，请重试或联系管理员', 'danger')

    return redirect(url_for('leads.index'))


@leads.route('/export')
def export():
    """导出Excel - 导出当前筛选条件下的所有线索"""
    query = _apply_filters(Lead.query)
    leads_list = query.order_by(Lead.publish_date.desc().nullslast()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = '线索列表'

    # 样式定义
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2C3E50', end_color='2C3E50', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )

    # 写表头
    headers = ['序号', '招标编号', '项目名称', '采购单位', '联系人', '电话',
               '预算金额(元)', '发布日期', '截止日期', '来源', '状态', '来源URL']
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # 写数据
    for row_idx, lead in enumerate(leads_list, 2):
        row_data = [
            row_idx - 1,
            lead.bidding_number or '',
            lead.project_name or '',
            lead.buyer_name or '',
            lead.contact_person or '',
            lead.phone or '',
            lead.budget_amount if lead.budget_amount is not None else '',
            lead.publish_date.strftime('%Y-%m-%d') if lead.publish_date else '',
            lead.deadline.strftime('%Y-%m-%d') if lead.deadline else '',
            lead.source_type or '',
            '已转化' if lead.is_converted else '未转化',
            lead.source_url or '',
        ]
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(vertical='center', wrap_text=True)

    # 自动列宽
    col_widths = [6, 22, 42, 25, 12, 15, 15, 13, 13, 10, 10, 42]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # 冻结首行
    ws.freeze_panes = 'A2'

    # 输出到内存
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'线索列表_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
