# -*- coding: utf-8 -*-
"""关键词注册表（纯配置，无逻辑）。

关键词按维度分类，各采集器按需组合引用。
"""

# ------------------------------------------------------------------
# 关键词分类
# ------------------------------------------------------------------
KEYWORD_CATEGORIES = {
    # 产品名称（直接搜索管道产品）
    'product': [
        '管道', 'PVC管', 'HDPE管', 'PPR管', 'PE管',
        '球墨铸铁管', '钢管', '波纹管', '混凝土管', '玻璃钢管',
        '双壁波纹管', '钢带增强管', '缠绕管', '克拉管',
        'PE给水管', 'PVC-U管', 'CPVC管', 'PB管', '塑料管',
    ],

    # 工程类型（管道作为主要材料出现）
    'engineering': [
        '给排水工程', '市政管网', '雨污分流', '供水管网',
        '排水管网', '燃气管网', '供热管网', '污水管网',
        '雨水管网', '消防管网', '综合管线', '地下管线',
    ],

    # 项目类型（管道需求密集的项目）
    'project': [
        '污水处理厂', '自来水厂', '海绵城市', '综合管廊',
        '市政道路', '工业园区', '水利工程', '引水工程',
        '灌溉工程', '河道治理', '水库除险加固',
    ],

    # 材料品类（更细分的产品词）
    'material': [
        '管材', '管件', '给水管', '排水管', '排污管',
        '电缆保护管', '通信管', '梅花管', '硅芯管',
    ],
}


def dedup_substring_keywords(keywords):
    """去除被其他关键词子串包含的冗余词，减少重复搜索。

    例如：'波纹管' ⊆ '双壁波纹管'，移除 '波纹管'；
          '给水管' ⊆ 'PE给水管'，移除 '给水管'。
    保留较长的关键词以扩大搜索覆盖面。
    """
    result = []
    for kw in keywords:
        if not any(other != kw and kw in other for other in keywords):
            result.append(kw)
    return result


# ------------------------------------------------------------------
# 各采集器使用的关键词组合
# ------------------------------------------------------------------

# 政府采购类采集器使用的关键词（产品 + 工程 + 材料，不含项目类型词）
# 项目类型词太宽泛，在政府采购搜索中会引入大量噪声
CCGP_KEYWORDS = (
    KEYWORD_CATEGORIES['product'] +
    KEYWORD_CATEGORIES['engineering'] +
    KEYWORD_CATEGORIES['material']
)

# 环评公示类采集器使用的关键词（侧重项目类型）
# 环评项目标题描述的是工程项目（如"XX污水处理厂建设项目环评公示"），
# 产品词（PVC管、HDPE管等）在环评标题中几乎不会出现，搜索只会浪费请求次数
# 仅保留"管道"——因为"管道工程"本身是项目名，在环评标题中确实会出现
EIA_KEYWORDS = (
    KEYWORD_CATEGORIES['project'] + ['管道']
)

# 招标平台类采集器使用的关键词（全部类别）
PLATFORM_KEYWORDS = (
    CCGP_KEYWORDS + KEYWORD_CATEGORIES['project']
)

# 去重后的最终关键词列表
CCGP_KEYWORDS_FINAL = dedup_substring_keywords(CCGP_KEYWORDS)
EIA_KEYWORDS_FINAL = dedup_substring_keywords(EIA_KEYWORDS)
PLATFORM_KEYWORDS_FINAL = dedup_substring_keywords(PLATFORM_KEYWORDS)

# 兼容旧 SCRAPER_KEYWORDS 的模块级常量（各采集器默认关键词）
DEFAULT_SCRAPER_KEYWORDS = PLATFORM_KEYWORDS_FINAL

# 公共资源交易平台类采集器使用的关键词（全部类别，含项目类型词）
# 工程建设类招标中管道作为材料出现，项目类型词（污水处理厂等）也是有效的搜索维度
GGZYJY_KEYWORDS = list(PLATFORM_KEYWORDS)

GGZYJY_KEYWORDS_FINAL = dedup_substring_keywords(GGZYJY_KEYWORDS)

# 管道商务网采集器使用的关键词（管道产品 + 工程 + 材料，与 CCGP 一致）
# 管道商务网是行业垂直平台，关键词侧重管道产品/工程/材料，不需要项目类型词
PIPEBIZ_KEYWORDS = list(CCGP_KEYWORDS)

PIPEBIZ_KEYWORDS_FINAL = dedup_substring_keywords(PIPEBIZ_KEYWORDS)

# 发改委项目审批采集器使用的关键词（与 EIA 相同，侧重项目类型词）
# 审批公示标题描述的是工程项目（如"XX污水处理厂建设项目备案公示"），
# 产品词（PVC管等）在审批标题中极少出现，仅保留项目类型词和"管道"
FDTZ_KEYWORDS = list(EIA_KEYWORDS)
FDTZ_KEYWORDS_FINAL = dedup_substring_keywords(FDTZ_KEYWORDS)

# 北极星环保网采集器使用的关键词（环保行业招投标/项目信息）
# 北极星环保频道涵盖：水处理、大气治理、固废、环境监测等细分领域
BJX_KEYWORDS = [
    '污水处理', '污水处理工程', '污水处理厂',
    '烟气脱硫', '烟气脱硝', '大气治理', '除尘设备',
    '固废处理', '垃圾焚烧', '危废处理', '污泥处理',
    '环保工程', '环保设备', '环保项目',
    '环境监测', '水质监测', '废气治理',
    '供水工程', '排水工程', '管网工程', '雨污分流',
    '河道治理', '水环境综合治理', '黑臭水体',
    '餐厨垃圾', '建筑垃圾', '生活垃圾',
]

BJX_KEYWORDS_FINAL = dedup_substring_keywords(BJX_KEYWORDS)
