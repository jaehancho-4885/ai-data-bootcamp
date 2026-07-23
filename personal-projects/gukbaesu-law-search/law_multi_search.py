import requests
from bs4 import BeautifulSoup

OC = "test"  # 승인 나면 개인 계정 OC로 교체

law_names = ["형법", "국가배상법", "민법"]  # 필요시 형사소송법도 (송치결정서 작성 근거)

search_url = "http://www.law.go.kr/DRF/lawSearch.do"
service_url = "http://www.law.go.kr/DRF/lawService.do"


def _text(node, default=None):
    return node.get_text(strip=True) if node else default


def find_exact_law(name):
    # display=100: 기본 20건이라 인기 법령은 뒤 페이지에 정확일치 항목이 있어 늘려서 조회
    params = {"OC": OC, "target": "eflaw", "type": "XML", "query": name, "display": 100}
    resp = requests.get(search_url, params=params, timeout=10)
    soup = BeautifulSoup(resp.content, features="xml")

    laws = soup.find_all("law")
    candidates = [_text(law.find("법령명한글"), "") for law in laws]

    for law in laws:
        if _text(law.find("법령명한글"), "") == name:
            return law, candidates
    return None, candidates


def fetch_articles(mst):
    params = {"OC": OC, "target": "eflaw", "MST": mst, "type": "XML"}
    resp = requests.get(service_url, params=params, timeout=10)
    soup = BeautifulSoup(resp.content, features="xml")

    articles = []
    for jo in soup.find_all("조문단위"):
        if _text(jo.find("조문여부")) != "조문":  # 장/절 제목 등 skip
            continue
        articles.append({
            "조번호": _text(jo.find("조문번호")),
            "조제목": _text(jo.find("조문제목")),
            "조문내용": _text(jo.find("조문내용")),
        })
    return articles


results = {}
for name in law_names:
    print(f"\n=== {name} ===")
    law, candidates = find_exact_law(name)

    if law is None:
        print(f"'{name}' 정확 일치 항목을 못 찾음. 검색된 후보 이름들: {candidates}")
        continue

    mst = _text(law.find("법령일련번호"))
    print(f"{name} MST: {mst}")

    articles = fetch_articles(mst)
    print(f"총 {len(articles)}개 조 파싱됨")
    for a in articles[:5]:
        print(a["조번호"], a["조제목"])

    results[name] = articles

print("\n처리 완료된 법령:", list(results.keys()))
