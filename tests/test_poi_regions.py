# -*- coding: utf-8 -*-
"""POI 地区配置（poi_regions）单元测试。"""
import pytest

from scraper import poi_regions


class TestGuangdongCities:
    """广东省城市列表测试。"""

    def test_guangdong_cities_count(self):
        """广东省应有 21 个地级市。"""
        assert len(poi_regions.GUANGDONG_CITIES) == 21

    def test_guangdong_cities_contains_major_cities(self):
        """广东省应包含主要城市。"""
        for city in ('广州', '深圳', '东莞', '佛山', '江门'):
            assert city in poi_regions.GUANGDONG_CITIES

    def test_get_guangdong_cities_returns_copy(self):
        """get_guangdong_cities() 应返回副本，修改不影响原列表。"""
        cities = poi_regions.get_guangdong_cities()
        cities.append('测试城市')
        assert '测试城市' not in poi_regions.GUANGDONG_CITIES


class TestNationalCities:
    """全国重点城市列表测试。"""

    def test_national_cities_not_empty(self):
        """每个省份至少应有 1 个城市。"""
        for province, cities in poi_regions.NATIONAL_CITIES.items():
            assert len(cities) >= 1, f'{province} 应有至少 1 个城市'

    def test_national_cities_contains_provinces(self):
        """应包含主要省份。"""
        for province in ('浙江', '江苏', '山东', '四川', '湖北'):
            assert province in poi_regions.NATIONAL_CITIES

    def test_national_cities_contains_municipalities(self):
        """应包含四个直辖市。"""
        for municipality in ('北京', '上海', '天津', '重庆'):
            assert municipality in poi_regions.NATIONAL_CITIES


class TestGetAllCities:
    """get_all_cities() 测试。"""

    def test_get_all_cities_count_greater_than_guangdong(self):
        """全部城市总数应大于广东省 21 城。"""
        all_cities = poi_regions.get_all_cities()
        assert len(all_cities) > 21

    def test_get_all_cities_includes_guangdong(self):
        """全部城市应包含广东省所有城市。"""
        all_cities = poi_regions.get_all_cities()
        for city in poi_regions.GUANGDONG_CITIES:
            assert city in all_cities

    def test_get_all_cities_includes_national(self):
        """全部城市应包含全国重点城市。"""
        all_cities = poi_regions.get_all_cities()
        # 随机抽查几个全国城市
        for city in ('杭州', '南京', '成都', '武汉'):
            assert city in all_cities


class TestGetCitiesByProvince:
    """get_cities_by_province() 测试。"""

    def test_get_cities_by_province_guangdong(self):
        """查询 '广东' 应返回 GUANGDONG_CITIES。"""
        cities = poi_regions.get_cities_by_province('广东')
        assert cities == poi_regions.GUANGDONG_CITIES

    def test_get_cities_by_province_zhejiang(self):
        """查询 '浙江' 应返回对应城市列表。"""
        cities = poi_regions.get_cities_by_province('浙江')
        assert cities == poi_regions.NATIONAL_CITIES['浙江']

    def test_get_cities_by_province_unknown(self):
        """查询不存在的省份应返回空列表。"""
        cities = poi_regions.get_cities_by_province('不存在的省份')
        assert cities == []

    def test_get_cities_by_province_returns_copy(self):
        """返回的列表应是副本，修改不影响原数据。"""
        cities = poi_regions.get_cities_by_province('浙江')
        cities.append('测试城市')
        assert '测试城市' not in poi_regions.NATIONAL_CITIES['浙江']


class TestGetBatchCities:
    """get_batch_cities() 分批逻辑测试。"""

    def test_batch_zero_starts_with_guangdong(self):
        """第 0 批应包含广东省。"""
        cities = poi_regions.get_batch_cities(0, batch_size=1)
        assert cities == poi_regions.GUANGDONG_CITIES

    def test_batch_size_3_first_batch(self):
        """batch_size=3 时，第 0 批应包含广东 + 前两个省份。"""
        cities = poi_regions.get_batch_cities(0, batch_size=3)
        # 广东(21) + 广西(5) + 福建(5) = 31
        assert len(cities) == 21 + 5 + 5
        # 应包含广东城市
        for city in ('广州', '深圳'):
            assert city in cities
        # 应包含广西城市
        assert '南宁' in cities
        # 应包含福建城市
        assert '福州' in cities

    def test_batch_out_of_range(self):
        """超出范围的批次应返回空列表。"""
        # 省份总数约 30+，batch_size=3 最多约 11 批，batch_index=100 肯定超出
        cities = poi_regions.get_batch_cities(100, batch_size=3)
        assert cities == []

    def test_all_batches_cover_all_cities(self):
        """所有批次合并后应覆盖全部城市（无遗漏）。"""
        batch_size = 3
        all_batch_cities = []
        batch_index = 0
        while True:
            batch = poi_regions.get_batch_cities(batch_index, batch_size=batch_size)
            if not batch:
                break
            all_batch_cities.extend(batch)
            batch_index += 1

        all_cities = poi_regions.get_all_cities()
        assert len(all_batch_cities) == len(all_cities)
        assert set(all_batch_cities) == set(all_cities)

    def test_batch_size_1_each_province_separate(self):
        """batch_size=1 时，每批只含一个省份。"""
        # 第 0 批：广东
        batch0 = poi_regions.get_batch_cities(0, batch_size=1)
        assert batch0 == poi_regions.GUANGDONG_CITIES
        # 第 1 批：第一个全国省份（广西）
        batch1 = poi_regions.get_batch_cities(1, batch_size=1)
        assert batch1 == poi_regions.NATIONAL_CITIES['广西']


class TestNoDuplicateCities:
    """城市无重复测试。"""

    def test_no_duplicate_in_guangdong(self):
        """广东省内无重复城市。"""
        assert len(poi_regions.GUANGDONG_CITIES) == len(set(poi_regions.GUANGDONG_CITIES))

    def test_no_duplicate_in_each_province(self):
        """每个省份内无重复城市。"""
        for province, cities in poi_regions.NATIONAL_CITIES.items():
            assert len(cities) == len(set(cities)), f'{province} 内有重复城市'

    def test_no_duplicate_across_all_cities(self):
        """全国范围内（广东+全国）无重复城市。"""
        all_cities = poi_regions.get_all_cities()
        assert len(all_cities) == len(set(all_cities)), \
            '存在重复城市: ' + str([c for c in all_cities if all_cities.count(c) > 1])


class TestGetCityCount:
    """get_city_count() 测试。"""

    def test_get_city_count_matches_all_cities(self):
        """get_city_count() 应等于 get_all_cities() 长度。"""
        assert poi_regions.get_city_count() == len(poi_regions.get_all_cities())

    def test_get_city_count_greater_than_21(self):
        """城市总数应大于 21。"""
        assert poi_regions.get_city_count() > 21


class TestGetBatchCount:
    """get_batch_count() 测试。"""

    def test_get_batch_count_default(self):
        """默认 batch_size=3 时，批次数应合理（> 5）。"""
        count = poi_regions.get_batch_count(batch_size=3)
        assert count > 5

    def test_get_batch_count_size_1(self):
        """batch_size=1 时，批次数等于省份数。"""
        count = poi_regions.get_batch_count(batch_size=1)
        assert count == poi_regions.get_province_count()

    def test_get_batch_count_large_size(self):
        """batch_size 足够大时，只需 1 批。"""
        count = poi_regions.get_batch_count(batch_size=100)
        assert count == 1
