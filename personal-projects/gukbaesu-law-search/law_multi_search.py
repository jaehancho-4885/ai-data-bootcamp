import requests
import xml.etree.ElementTree as ET

OC = "test"  # 승인 나면 johnny4885로 교체

law_names = ["형법", "국가배상법", "민법"]  # 필요시 형사소송법도 (송치결정서 작성 근거)

search_url = "http://www.law.go.kr/DRF/lawSearch.do"
service_url = "http://www.law.go.kr/DRF/lawService.do"


def find_exact_law(name):
    params = {"OC": OC, "target": "eflaw", "type": "XML", "query": name}
    resp = requests.get(search_url, params=params, timeout=10)
    root = ET.fromstring(resp.content)

    candidates = [law.findtext("법령명한글", "").strip() for law in root.findall("law")]

    for law in root.findall("law"):
        law_name = law.findtext("법령명한글", "").strip()
        if law_name == name:
            return law, candidates
    return None, candidates


def fetch_articles(mst):
    params = {"OC": OC, "target": "eflaw", "MST": mst, "type": "XML"}
    resp = requests.get(service_url, params=params, timeout=10)
    root = ET.fromstring(resp.content)

    articles = []
    for jo in root.iter("조문단위"):
        if jo.findtext("조문여부") != "조문":  # 장/절 제목 등 skip
            continue
        articles.append({
            "조번호": jo.findtext("조문번호"),
            "조제목": jo.findtext("조문제목"),
            "조문내용": jo.findtext("조문내용"),
        })
    return articles


results = {}
for name in law_names:
    print(f"\n=== {name} ===")
    law, candidates = find_exact_law(name)

    if law is None:
        print(f"'{name}' 정확 일치 항목을 못 찾음. 검색된 후보 이름들: {candidates}")
        continue

    mst = law.findtext("법령일련번호")
    print(f"{name} MST: {mst}")

    articles = fetch_articles(mst)
    print(f"총 {len(articles)}개 조 파싱됨")
    for a in articles[:5]:
        print(a["조번호"], a["조제목"])

    results[name] = articles

print("\n처리 완료된 법령:", list(results.keys()))
