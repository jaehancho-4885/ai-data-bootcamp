# ─────────────────────────────────────────────
# PERCENT SCIENCE - Anti-Aging Line 스크래핑 초안
# 대상: https://percentscience.com/collections/anti-aging-line
# 수집 항목:
#   [컬렉션 페이지] 상품명, 정가, 할인가, 할인율(%), 상품 URL
#   [개별 상품 페이지] 리뷰 존재 여부, 리뷰 개수 (Judge.me 위젯 기반)
#
# 실제 DOM 구조는 Playwright로 직접 렌더링해서 확인해 반영했습니다.
# (주의) a.resource-card / .resource-card__title 는 검색창을 열 때만 보이는
#        predictive-search 미리보기용 숨겨진 마크업이라 실제 그리드가 아니었습니다.
#        Shopify Horizon 테마는 실제 그리드에 <product-card> 커스텀 엘리먼트를 씁니다.
#   - 상품 카드   : product-card  (화면에 실제로 보이는 것만 이 태그로 렌더링됨)
#   - 링크        : a.product-card__link[href^="/products/"]
#   - 상품명      : product-card 내부 img의 alt 속성 (제목 블록 class는 빌드마다 해시가 달라 불안정)
#   - 정가(취소선): product-price 안의 s.compare-at-price (할인 없으면 없음)
#   - 할인가      : product-price 안의 span.price
#   - 리뷰 위젯   : div.jdgm-rev-widg[data-number-of-reviews][data-average-rating]
#     (Judge.me. "더 보기"로 추가 로드되는 리뷰가 있어도 data-number-of-reviews 값이
#      전체 개수를 담고 있어 이 속성을 우선 신뢰합니다)
#
# Playwright가 없는 환경에서도 노트북/스크립트가 끝까지 실행되도록,
# 사전에 저장해 둔 샘플 HTML로 파싱 로직만 데모 실행하는 폴백을 포함합니다.
# ─────────────────────────────────────────────

import re
import time

import pandas as pd

COLLECTION_URL = "https://percentscience.com/collections/anti-aging-line"
OUTPUT_CSV = "percentscience_anti_aging_products.csv"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_DELAY_SEC = 1.5  # 상품 상세 페이지 이동 사이 최소 대기 시간 (서버 부하 방지)

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def parse_price(text):
    """'$128.00' 같은 문자열에서 숫자만 뽑아 float으로 변환. 없으면 None."""
    if not text:
        return None
    match = re.search(r"[\d,]+\.?\d*", text)
    if not match:
        return None
    return float(match.group().replace(",", ""))


def compute_discount_rate(regular_price, sale_price):
    """정가 대비 할인율(%). 정가가 없거나 할인가보다 작으면 0.0으로 처리."""
    if not regular_price or not sale_price or regular_price <= sale_price:
        return 0.0
    return round((regular_price - sale_price) / regular_price * 100, 1)


def extract_products_from_collection(page):
    """컬렉션 페이지에서 상품명 / 정가 / 할인가 / 할인율 / URL 목록을 추출."""
    page.goto(COLLECTION_URL, wait_until="networkidle")
    page.wait_for_selector("product-card", timeout=15000)

    cards = page.locator("product-card").all()
    products = []
    seen_urls = set()

    for card in cards:
        link = card.locator("a.product-card__link").first
        href = link.get_attribute("href")
        if not href or "/products/" not in href:
            continue
        product_url = "https://percentscience.com" + href.split("?")[0]
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        name = card.locator("img").first.get_attribute("alt").strip()

        compare_locator = card.locator("s.compare-at-price")
        regular_price = parse_price(compare_locator.first.inner_text()) if compare_locator.count() else None

        price_locator = card.locator("span.price")
        sale_price = parse_price(price_locator.first.inner_text()) if price_locator.count() else None

        # 취소선 정가가 없는 상품은 할인이 없는 상품 -> 정가 = 판매가
        if regular_price is None:
            regular_price = sale_price

        products.append({
            "상품명": name,
            "정가": regular_price,
            "할인가": sale_price,
            "할인율(%)": compute_discount_rate(regular_price, sale_price),
            "상품URL": product_url,
        })

    return products


def check_reviews(page, product_url):
    """개별 상품 페이지에서 리뷰 존재 여부와 개수를 확인 (Judge.me 위젯 기준)."""
    page.goto(product_url, wait_until="networkidle")

    widget = page.locator("div.jdgm-rev-widg").first
    review_count = 0

    if widget.count() > 0:
        raw_count = widget.get_attribute("data-number-of-reviews")
        if raw_count and raw_count.isdigit():
            review_count = int(raw_count)

    # data-number-of-reviews 속성이 없는 예외 상황을 위한 폴백: 실제 렌더링된 리뷰 블록 수
    if review_count == 0:
        review_count = page.locator("div.jdgm-rev").count()

    has_reviews = review_count > 0
    return has_reviews, review_count


def scrape_with_playwright():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        products = extract_products_from_collection(page)
        print(f"[수집] 상품 {len(products)}개 발견, 리뷰 정보 확인 중...")

        for i, product in enumerate(products, start=1):
            try:
                has_reviews, review_count = check_reviews(page, product["상품URL"])
            except Exception as e:
                print(f"  - [{i}/{len(products)}] 리뷰 확인 실패: {product['상품명']} ({e})")
                has_reviews, review_count = False, 0

            product["리뷰존재여부"] = has_reviews
            product["리뷰개수"] = review_count
            print(f"  - [{i}/{len(products)}] {product['상품명']}: 리뷰 {review_count}개")

            time.sleep(REQUEST_DELAY_SEC)

        browser.close()
        return products


# ─────────────────────────────────────────────
# Playwright 미설치 시 폴백: 사전에 저장해 둔 샘플 HTML로 파싱 로직만 데모
# (실제 크롤링이 아니라, BeautifulSoup 기반 파싱 흐름 검증용)
# ─────────────────────────────────────────────
FALLBACK_COLLECTION_HTML = """
<product-card>
  <a class="product-card__link" href="/products/avocool-2-6-sun-screen-serum">
    <img alt="Avocool-2.6 Sun Screen Serum 40ml" src="dummy.jpg">
    <product-price>
      <s class="compare-at-price">$28.00</s>
      <span class="price">$22.00</span>
    </product-price>
  </a>
</product-card>
<product-card>
  <a class="product-card__link" href="/products/cellinol-5-cream-2-0-oz">
    <img alt="CELLINOL-5(tm) CREAM 2.0 Oz. (60ml)" src="dummy.jpg">
    <product-price>
      <span class="price">$128.00</span>
    </product-price>
  </a>
</product-card>
"""

FALLBACK_PRODUCT_HTML = """
<div class='jdgm-rev-widg' data-average-rating='4.85' data-number-of-reviews='26'></div>
"""


def scrape_with_fallback():
    from bs4 import BeautifulSoup

    print("[폴백] Playwright가 없어 저장된 샘플 HTML로 파싱 로직만 데모 실행합니다.")
    soup = BeautifulSoup(FALLBACK_COLLECTION_HTML, "html.parser")
    products = []

    for card in soup.select("product-card"):
        link = card.select_one("a.product-card__link")
        href = link.get("href")
        product_url = "https://percentscience.com" + href
        name = card.select_one("img").get("alt").strip()

        compare_tag = card.select_one("s.compare-at-price")
        regular_price = parse_price(compare_tag.get_text()) if compare_tag else None

        price_tag = card.select_one("span.price")
        sale_price = parse_price(price_tag.get_text()) if price_tag else None

        if regular_price is None:
            regular_price = sale_price

        products.append({
            "상품명": name,
            "정가": regular_price,
            "할인가": sale_price,
            "할인율(%)": compute_discount_rate(regular_price, sale_price),
            "상품URL": product_url,
        })

    # 리뷰는 샘플 상품 페이지 하나로만 데모
    review_soup = BeautifulSoup(FALLBACK_PRODUCT_HTML, "html.parser")
    widget = review_soup.select_one("div.jdgm-rev-widg")
    review_count = int(widget["data-number-of-reviews"]) if widget else 0

    for product in products:
        product["리뷰존재여부"] = review_count > 0
        product["리뷰개수"] = review_count

    return products


def main():
    if HAS_PLAYWRIGHT:
        products = scrape_with_playwright()
    else:
        products = scrape_with_fallback()

    df = pd.DataFrame(products)
    print(df)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[저장 완료] {OUTPUT_CSV} ({len(df)}행)")


if __name__ == "__main__":
    main()
