# -*- coding: utf-8 -*-
"""项目全生命周期追踪。

通过项目名称模糊匹配，自动关联同一项目在不同阶段（环评/招标/中标/验收）的公告。
匹配结果存入 Lead.raw_data JSON 中的 related_leads 字段。
"""
import json
import logging
import re

from scraper.utils import extract_field, strip_stage_suffix, tokenized_bigrams

logger = logging.getLogger(__name__)

# 空白字符统一
_WS_RE = re.compile(r'\s+')


def normalize_project_name(name):
    """项目名称标准化：去除常见阶段前后缀、统一空白字符。

    例如：
    - "XX市污水处理厂建设项目环评公示" → "XX市污水处理厂建设项目"
    - "XX市污水处理厂建设项目招标公告" → "XX市污水处理厂建设项目"
    - "  XX市污水处理厂  " → "XX市污水处理厂"

    Args:
        name: 原始项目名称字符串

    Returns:
        str: 标准化后的项目名称；输入为空时返回空字符串
    """
    if not name:
        return ''
    name = _WS_RE.sub('', str(name).strip())
    if not name:
        return ''
    return strip_stage_suffix(name)


def calculate_similarity(name1, name2):
    """计算两个项目名称的相似度（0.0-1.0）。

    使用 Jaccard 相似度：先按常见标点拆分为多个词段，再对每段生成 2-gram
    字符集，最终取所有段的 2-gram 并集计算 Jaccard 比值。
    不引入外部依赖（如 fuzzywuzzy）。

    分词策略：按括号、破折号、冒号、斜杠、空格等分隔符将名称拆成多段，
    每段内部生成 2-gram，避免跨段拼接产生虚假匹配。
    例如 "XX(污水处理厂)" 与 "污水处理厂(XX)" 分词后均为 ["XX", "污水处理厂"]，
    2-gram 集合完全相同，相似度 1.0；而连续字符串 "XX污水处理厂" 因跨边界
    产生 "X污" 等 2-gram，与前者相似度较低，不会被误判为相同项目。

    Args:
        name1: 第一个项目名称
        name2: 第二个项目名称

    Returns:
        float: 相似度，范围 [0.0, 1.0]
    """
    s1 = str(name1).strip() if name1 else ''
    s2 = str(name2).strip() if name2 else ''
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    grams1 = tokenized_bigrams(s1)
    grams2 = tokenized_bigrams(s2)
    if not grams1 or not grams2:
        # 单字符名称回退为精确比较
        return 1.0 if s1 == s2 else 0.0
    intersection = grams1 & grams2
    union = grams1 | grams2
    return len(intersection) / len(union)


def find_related_leads(new_lead, existing_leads, threshold=0.7):
    """在已有 Lead 列表中查找与 new_lead 项目名称相似的记录。

    纯函数，不访问数据库。

    Args:
        new_lead: 新入库的 Lead 对象（或 dict），需含 project_name 字段
        existing_leads: 已有 Lead 列表（建议按 buyer_name 预筛选）
        threshold: 相似度阈值（默认 0.7），低于此值的匹配被过滤

    Returns:
        list[dict]: 匹配的 Lead 信息列表
            [{'lead_id': int, 'project_name': str, 'similarity': float}]
    """
    new_name = normalize_project_name(extract_field(new_lead, 'project_name'))
    if not new_name:
        return []

    new_id = extract_field(new_lead, 'id')
    results = []
    for candidate in existing_leads:
        cand_id = extract_field(candidate, 'id')
        # 跳过自身
        if new_id and cand_id and new_id == cand_id:
            continue
        cand_name = normalize_project_name(extract_field(candidate, 'project_name'))
        if not cand_name:
            continue
        sim = calculate_similarity(new_name, cand_name)
        if sim >= threshold:
            results.append({
                'lead_id': cand_id,
                'project_name': extract_field(candidate, 'project_name'),
                'similarity': round(sim, 4),
            })

    # 按相似度降序排列
    results.sort(key=lambda x: x['similarity'], reverse=True)
    return results


def enrich_lead_with_relations(lead_id, app):
    """为指定 Lead 查找并写入关联线索。

    1. 从数据库加载该 Lead
    2. 查找同 buyer_name 的其他 Lead（LIMIT 50，避免大查询）
    3. 对每条候选 Lead 计算项目名称相似度
    4. 将匹配结果写入 raw_data.related_leads
    5. 保存

    Args:
        lead_id: Lead 主键 ID
        app: Flask app 实例（用于数据库操作）

    Returns:
        int: 关联到的线索数量；-1 表示 Lead 不存在
    """
    from app.models import Lead
    from app.extensions import db

    with app.app_context():
        lead = db.session.get(Lead, lead_id)
        if lead is None:
            logger.warning('[lifecycle] Lead 不存在: %s', lead_id)
            return -1

        buyer_name = (lead.buyer_name or '').strip()
        query = Lead.query.filter(Lead.id != lead_id, Lead.deleted == False)  # noqa: E712
        if buyer_name:
            query = query.filter(Lead.buyer_name == buyer_name)
        candidates = query.limit(50).all()

        related = find_related_leads(lead, candidates)

        # 读取已有 raw_data，合并写入
        try:
            raw = json.loads(lead.raw_data) if lead.raw_data else {}
        except (json.JSONDecodeError, TypeError):
            raw = {}
        raw['related_leads'] = related
        lead.raw_data = json.dumps(raw, ensure_ascii=False, default=str)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('[lifecycle] 保存关联信息失败: lead_id=%s', lead_id)
            raise

        logger.info('[lifecycle] lead_id=%s 关联到 %d 条线索', lead_id, len(related))
        return len(related)


def batch_enrich_leads(source_type, app, since_date=None):
    """批量为指定来源的 Lead 补充关联信息。

    在采集完成后调用，为该来源最近入库的 Lead 逐一查找关联。

    Args:
        source_type: 来源类型（ccgp/gdgpo/eia/ggzyjy）
        app: Flask app 实例
        since_date: 仅处理此日期之后发布的 Lead（date 对象）；为 None 时处理最近 200 条

    Returns:
        int: 处理的 Lead 数量
    """
    from app.models import Lead

    with app.app_context():
        query = Lead.query.filter(
            Lead.source_type == source_type,
            Lead.deleted == False,  # noqa: E712
        )
        if since_date is not None:
            query = query.filter(Lead.publish_date >= since_date)
        leads = query.order_by(Lead.id.desc()).limit(200).all()

        count = 0
        for lead in leads:
            try:
                enrich_lead_with_relations(lead.id, app)
                count += 1
            except Exception:
                logger.exception('[lifecycle] 批量关联处理失败: lead_id=%s', lead.id)

        logger.info('[lifecycle] 批量关联完成: source=%s, 处理 %d 条', source_type, count)
        return count
