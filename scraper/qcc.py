# -*- coding: utf-8 -*-
"""企查查开放平台 API 集成（企业画像数据查询）

企查查（openapi.qcc.com）提供付费 REST API，用于查询企业工商信息、股东、
失信核查等画像数据。本模块实现框架性集成：

- API 平台：https://openapi.qcc.com
- 认证方式：Bearer Token / API Key（通过环境变量 QCC_API_KEY 注入）
- 付费接口：不纳入每日全量采集（include_in_all=False），仅在手动触发时运行

已知 API 接口（ApiCode / 单价）：
- 企业模糊搜索：886 / 0.10 元/次
- 企业工商信息：410 / 0.20 元/次
- 失信核查：    740 / 0.30 元/次

调用前先通过 _query_api 统一封装请求（认证头 + 错误处理），各接口方法
（search_company / get_business_info / get_dishonest_info）在内部复用。
"""
import json
import logging
import time
from datetime import date, datetime

from scraper.base import BaseScraper, ScraperStopped

logger = logging.getLogger(__name__)

_BASE_URL = 'https://openapi.qcc.com'

# 企查查 API 接口编码（TODO: 以官方文档为准，确认后固化）
_API_CODE_SEARCH = '886'      # 企业模糊搜索
_API_CODE_BUSINESS = '410'    # 企业工商信息
_API_CODE_DISHONEST = '740'   # 失信核查


class QccScraper(BaseScraper):
    """企查查开放平台 API 采集器（企业画像查询，付费接口）

    设计说明：
    - 不参与定时全量采集，仅手动触发
    - 严格前置去重：调用前先查本地 DB 确认公司是否已有画像记录
    - 日限额控制：到达 QCC_DAILY_LIMIT 自动停止
    - API Key 检查：未配置时记录日志并优雅退出（不报错）
    - 查询结果写入 Lead 的 raw_data 字段（JSON 序列化保存）
    """

    source_type = 'qcc'
    base_url = _BASE_URL
    referer = ''

    def __init__(self, app=None):
        super().__init__(app=app)
        self.api_key = ''
        self.daily_limit = 100
        # 今日已消耗次数（进程内计数，重启归零；生产环境可改为持久化）
        self._daily_used = 0
        self._daily_date = date.today()
        if app:
            self.api_key = app.config.get('QCC_API_KEY', '')
            self.daily_limit = app.config.get('QCC_DAILY_LIMIT', 100)

    # ------------------------------------------------------------------
    # 主流程（覆写 BaseScraper.run，适配非关键词翻页的 API 查询模式）
    # ------------------------------------------------------------------
    def run(self, keywords=None, max_pages=5):
        """执行企查查画像查询主流程

        Args:
            keywords: 可选，手动传入公司名列表；为 None 时自动从 Lead 表
                      提取缺少画像的 buyer_name
            max_pages: 未使用（保持接口兼容）

        Returns:
            int: 成功查询并写入的记录数
        """
        # 前置检查：API Key 是否配置
        if not self.api_key:
            logger.info('[qcc] 未配置 QCC_API_KEY，跳过企查查采集（请通过环境变量注入）')
            return 0

        logger.info('[qcc] 开始企查查画像查询，日限额: %d', self.daily_limit)

        # 1. 创建任务记录
        task = self.create_task(self.source_type, self.base_url)
        task_id = task.id
        self._progress_start(task_id, 1, 1)

        total_new = 0
        try:
            self._create_session()

            # 2. 确定待查询的公司名列表
            company_names = self._get_pending_companies(keywords)
            if not company_names:
                logger.info('[qcc] 无待查询公司，任务结束')
                self.update_task(task_id, '完成', result_count=0)
                self._progress_finish('完成', collected=0)
                return 0

            logger.info('[qcc] 待查询公司数: %d', len(company_names))
            self._progress_update(
                message='共 %d 家待查询公司' % len(company_names),
            )

            # 3. 逐个查询
            for idx, company_name in enumerate(company_names, start=1):
                self._check_pause_and_stop()

                # 日限额检查
                if self._daily_used >= self.daily_limit:
                    logger.info('[qcc] 已达今日限额 %d，停止查询', self.daily_limit)
                    break

                # 前置去重：再次确认本地无画像（防止并发写入）
                if self._has_profile(company_name):
                    logger.debug('[qcc] 跳过已有画像: %s', company_name)
                    continue

                self._progress_update(
                    message='查询 %s (%d/%d)' % (company_name, idx, len(company_names)),
                )

                result = self._query_company(company_name)
                if result is not None:
                    saved = self._save_profile(company_name, result)
                    if saved:
                        total_new += 1
                        logger.info('[qcc] 已保存画像: %s', company_name)

                self._daily_used += 1

            # 4. 更新任务状态
            self.update_task(task_id, '完成', result_count=total_new)
            self._progress_finish('完成', collected=total_new)
            logger.info('[qcc] 查询完成，新增画像 %d 条（今日消耗 %d 次）',
                        total_new, self._daily_used)
            return total_new

        except ScraperStopped:
            logger.info('[qcc] 查询已被手动停止，累计新增 %d 条', total_new)
            self.update_task(task_id, '已停止', result_count=total_new)
            self._progress_finish('已停止', collected=total_new)
            return total_new

        except Exception as e:
            logger.exception('[qcc] 查询异常: %s', e)
            self.update_task(task_id, '失败', result_count=total_new, error_msg=str(e))
            self._progress_finish('失败', collected=total_new, error_msg=str(e))
            return total_new
        finally:
            self._close_session()
            self._progress_clear_control()

    # ------------------------------------------------------------------
    # 待查询公司名获取
    # ------------------------------------------------------------------
    def _get_pending_companies(self, keywords=None):
        """获取待查询公司名列表（去重后）

        优先使用传入的 keywords；否则从 Lead 表提取 buyer_name 不为空且
        source_type != 'qcc' 的记录（即缺少企查查画像的采购单位），去重后返回。

        Args:
            keywords: 手动指定的公司名列表

        Returns:
            list[str]: 去重后的公司名列表
        """
        if keywords:
            # 手动指定时直接使用
            return list({name.strip() for name in keywords if name and name.strip()})

        try:
            from app.models import Lead
            # 查找所有 buyer_name 非空、且不是 qcc 来源的 lead，提取唯一公司名
            rows = (
                Lead.query
                .filter(
                    Lead.buyer_name.isnot(None),
                    Lead.buyer_name != '',
                    Lead.source_type != 'qcc',
                    Lead.deleted != True,  # noqa: E712
                )
                .with_entities(Lead.buyer_name)
                .distinct()
                .all()
            )
            names = [row[0].strip() for row in rows if row[0] and row[0].strip()]
            # 过滤掉已有 qcc 画像的公司
            existing = self._get_profiled_companies(names)
            return [n for n in names if n not in existing]
        except Exception:
            logger.exception('[qcc] 获取待查询公司名失败')
            return []

    def _get_profiled_companies(self, names):
        """查询哪些公司已有 qcc 来源的画像记录

        Args:
            names: 公司名列表

        Returns:
            set[str]: 已有画像的公司名集合
        """
        if not names:
            return set()
        try:
            from app.models import Lead
            rows = (
                Lead.query
                .filter(
                    Lead.source_type == 'qcc',
                    Lead.buyer_name.in_(names),
                )
                .with_entities(Lead.buyer_name)
                .all()
            )
            return {row[0] for row in rows}
        except Exception:
            logger.warning('[qcc] 查询已有画像失败，回退为空集', exc_info=True)
            return set()

    def _has_profile(self, company_name):
        """检查单个公司是否已有 qcc 画像记录"""
        try:
            from app.models import Lead
            return Lead.query.filter_by(
                source_type='qcc', buyer_name=company_name
            ).first() is not None
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 企查查 API 调用（占位实现，需查阅官方文档后补全）
    # ------------------------------------------------------------------
    def _query_api(self, api_code, params=None):
        """统一封装企查查 API 请求

        Args:
            api_code: 接口编码（如 '886', '410', '740'）
            params: 查询参数 dict

        Returns:
            dict | None: API 返回的 JSON 数据，失败返回 None

        TODO: 查阅企查查开放平台官方文档，确认：
        1. 请求 URL 格式（推测为 /api/{apiCode} 或 /services/open/{apiCode}）
        2. 认证头格式（Bearer Token vs. X-Api-Key vs. query param key）
        3. 响应结构（成功/失败的 JSON 字段名）
        """
        if self.session is None:
            self._create_session()

        # TODO: 以下 URL 和认证方式为占位，需替换为官方文档确认的格式
        url = '%s/api/%s' % (_BASE_URL, api_code)
        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

        try:
            time.sleep(self.get_random_delay())
            response = self.session.get(url, params=params, headers=headers)
            if response.status_code == 200:
                payload = response.json()
                # TODO: 根据官方文档确认成功响应的判断字段
                if payload.get('Status') == '200' or payload.get('code') == 200:
                    return payload.get('Result') or payload.get('result') or payload
                logger.warning('[qcc] API %s 返回业务错误: %s', api_code, payload)
                return None
            else:
                logger.warning('[qcc] API %s HTTP %d', api_code, response.status_code)
                return None
        except Exception as e:
            logger.warning('[qcc] API %s 请求异常: %s', api_code, e)
            return None

    def search_company(self, company_name):
        """企业模糊搜索（ApiCode 886，0.10 元/次）

        Args:
            company_name: 公司名称（支持模糊匹配）

        Returns:
            list[dict] | None: 匹配的企业列表，失败返回 None
        """
        # TODO: 参数名以官方文档为准（searchKey / keyword / name 等）
        result = self._query_api(_API_CODE_SEARCH, {'searchKey': company_name})
        if result is None:
            return None
        # TODO: 解析返回结构，提取企业列表
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get('ResultList') or result.get('list') or [result]
        return None

    def get_business_info(self, company_name):
        """企业工商信息查询（ApiCode 410，0.20 元/次）

        Args:
            company_name: 公司全称

        Returns:
            dict | None: 工商信息，失败返回 None
        """
        # TODO: 参数名以官方文档为准
        return self._query_api(_API_CODE_BUSINESS, {'keyword': company_name})

    def get_dishonest_info(self, company_name):
        """失信核查（ApiCode 740，0.30 元/次）

        Args:
            company_name: 公司全称

        Returns:
            dict | None: 失信信息，失败返回 None
        """
        # TODO: 参数名以官方文档为准
        return self._query_api(_API_CODE_DISHONEST, {'keyword': company_name})

    # ------------------------------------------------------------------
    # 查询 + 保存
    # ------------------------------------------------------------------
    def _query_company(self, company_name):
        """对单个公司执行画像查询（搜索 + 工商信息），合并结果

        Args:
            company_name: 公司名称

        Returns:
            dict | None: 合并后的画像数据，查询失败返回 None
        """
        # 第一步：模糊搜索确认企业存在（消耗 1 次搜索配额）
        search_results = self.search_company(company_name)
        if not search_results:
            logger.debug('[qcc] 未找到: %s', company_name)
            return None

        # 取搜索结果中匹配度最高的第一条
        top_match = search_results[0] if isinstance(search_results, list) else search_results

        profile = {
            'company_name': company_name,
            'search_result': top_match,
            'query_time': datetime.now().isoformat(),
        }

        # 第二步：查询工商信息（消耗 1 次工商配额）
        # TODO: 根据实际需要决定是否同时查询工商/失信
        # business_info = self.get_business_info(company_name)
        # if business_info:
        #     profile['business_info'] = business_info
        #     self._daily_used += 1  # 额外消耗一次

        return profile

    def _save_profile(self, company_name, profile_data):
        """将画像结果写入 Lead 表（source_type='qcc'）

        Args:
            company_name: 公司名称
            profile_data: 画像数据 dict

        Returns:
            bool: 是否保存成功
        """
        try:
            from app.models import Lead
            from app.extensions import db

            lead = Lead(
                project_name='企业画像: %s' % company_name[:480],
                buyer_name=company_name[:200],
                announcement_type='企业画像',
                source_type='qcc',
                source_url='',
                raw_data=json.dumps(profile_data, ensure_ascii=False, default=str),
                publish_date=date.today(),
            )
            db.session.add(lead)
            db.session.commit()
            return True
        except Exception as e:
            logger.warning('[qcc] 保存画像失败 (%s): %s', company_name, e)
            try:
                from app.extensions import db
                db.session.rollback()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # 未使用的 BaseScraper 钩子（保持接口兼容）
    # ------------------------------------------------------------------
    def _scrape_page(self, keyword, page):
        """企查查不使用关键词翻页模式，此方法不会被调用"""
        return []
