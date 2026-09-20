import time
from datetime import datetime, timedelta
import numpy as np
import requests


class RefurbPriceAnalyzer:

    def __init__(self):
        # 번개장터 검색 API 엔드포인트
        self.bunjang_api_url = (
            'https://api.bunjang.co.kr/api/1/find_v2.json'
        )
        # 이상치 필터링용 제외 키워드 목록
        self.exclude_keywords = [
            '부품용',
            '정크',
            '계정락',
            '액정파손',
            '구매글',
            '삽니다',
            '구합니다',
            '수리건',
            '매입',
            '케이스',
            '파우치',
        ]

    def fetch_sold_items(self, query: str, max_pages: int = 3):
        """번개장터에서 '판매 완료' 상태인 매물만 수집 (status=3)"""
        sold_items = []

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        }

        for page in range(max_pages):
            params = {
                'q': query,
                'order': 'date',  # 최신순
                'page': page,
                'n': 50,  # 한 페이지당 50개
                'stat_device': 'w',
                'stat_category_required': '1',
            }

            try:
                response = requests.get(
                    self.bunjang_api_url,
                    params=params,
                    headers=headers,
                    timeout=5,
                )
                if response.status_code != 200:
                    break

                data = response.json()
                items = data.get('list', [])

                if not items:
                    break

                for item in items:
                    # status: 3 = 판매 완료 (1 = 판매 중)
                    # status, price, update_time 등 확인
                    is_sold = item.get('status') == '3' or item.get(
                        'status_name'
                    ) in ['판매완료', '거래완료']

                    if is_sold:
                        title = item.get('name', '')
                        price = int(item.get('price', 0))
                        update_time = item.get(
                            'update_time', 0
                        )  # Unix Timestamp (초 단위)

                        sold_items.append({
                            'title': title,
                            'price': price,
                            'timestamp': update_time,
                            'date': datetime.fromtimestamp(update_time),
                        })

                time.sleep(0.3)  # Rate Limit 방지용 예외 대기

            except Exception as e:
                print(f'[Error] API 요청 실패: {e}')
                break

        return sold_items

    def filter_by_period(self, items: list, months: int = 3):
        """선택한 기간(N개월) 이내의 실거래 내역만 필터링"""
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        filtered = [item for item in items if item['date'] >= cutoff_date]
        return filtered

    def filter_junk_keywords(self, items: list):
        """부품용, 파손, 구매글 등 노이즈 데이터 제거"""
        valid_items = []
        for item in items:
            title = item['title'].lower()
            if any(
                keyword in title for keyword in self.exclude_keywords
            ):  # 제외 키워드 포함 시 탈락
                continue
            if item['price'] < 30000:  # 터무니없이 낮은 가격(단순 부품) 제외
                continue
            valid_items.append(item)
        return valid_items

    def remove_statistical_outliers(self, prices: list):
        """IQR(사분위수) 알고리즘을 사용해 지나치게 낮거나 높은 가격(이상치) 제거"""
        if len(prices) < 4:
            return prices

        q25, q75 = np.percentile(prices, [25, 75])
        iqr = q75 - q25
        lower_bound = q25 - (1.5 * iqr)
        upper_bound = q75 + (1.5 * iqr)

        return [p for p in prices if lower_bound <= p <= upper_bound]

    def get_market_price_report(
        self, model: str, ram: str, ssd: str, months: int = 3
    ):
        """[통합 실행 함수] UI에서 백엔드로 요청하는 핵심 메인 함수"""
        search_query = f'{model} {ram} {ssd}'.strip()

        # 1. 판매 완료 데이터 가져오기
        raw_items = self.fetch_sold_items(search_query, max_pages=4)

        # 2. 최근 N개월 기간 필터링
        period_filtered = self.filter_by_period(raw_items, months=months)

        # 3. 정크/부품/구매글 키워드 필터링
        clean_items = self.filter_junk_keywords(period_filtered)

        if not clean_items:
            return {
                'success': False,
                'message': (
                    f"'{search_query}'에 대한 최근 {months}개월간 판매 완료"
                    ' 데이터가 충분하지 않습니다.'
                ),
            }

        raw_prices = [item['price'] for item in clean_items]

        # 4. 통계 이상치 제거
        filtered_prices = self.remove_statistical_outliers(raw_prices)

        # 5. 지표 계산
        avg_price = int(np.mean(filtered_prices))
        median_price = int(np.median(filtered_prices))
        min_price = int(np.min(filtered_prices))
        max_price = int(np.max(filtered_prices))

        # 10,000원 단위 반올림 처리 (실제 사용하기 편한 시세로 변환)
        recommended_base_price = round(avg_price, -4)

        return {
            'success': True,
            'query': search_query,
            'months': months,
            'total_completed_sales': len(clean_items),
            'recommended_base_price': recommended_base_price,  # A급 기준 추천 시세
            'stats': {
                'average': avg_price,
                'median': median_price,
                'min': min_price,
                'max': max_price,
            },
            'sample_data': clean_items[:5],  # 최근 거래 5건 샘플
        }


# ==========================================
# 🧪 테스트 실행 코드 (로컬 단독 테스트용)
# ==========================================
if __name__ == '__main__':
    analyzer = RefurbPriceAnalyzer()

    # 예시: 맥북에어 M1 8GB 256GB의 최근 3개월 실거래가 조회
    result = analyzer.get_market_price_report(
        model='맥북에어 M1', ram='8G', ssd='256G', months=3
    )

    if result['success']:
        print('=== 📊 실거래가 분석 리포트 ===')
        print(f"🔍 검색 조건: {result['query']}")
        print(
            f"🗓️ 분석 기간: 최근 {result['months']}개월 내 판매 완료 매물"
            ''
        )
        print(f"📦 최종 반영 건수: {result['total_completed_sales']}건")
        print(
            '💡 추천 A급 순정 기준가:'
            f" {result['recommended_base_price']:,}원"
        )
        print(
            f"📈 거래 범위: {result['stats']['min']:,}원 ~"
            f" {result['stats']['max']:,}원"
        )
    else:
        print(result['message'])
