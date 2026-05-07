import os
import requests
from bs4 import BeautifulSoup
import time

def scrape_cbtbank():
    base_url = "https://cbtbank.kr"
    category_url = f"{base_url}/category/%ED%86%A0%EB%AA%A9%EA%B8%B0%EC%82%AC"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    
    print("목록을 가져오는 중...")
    try:
        resp = requests.get(category_url, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser') 
    except Exception as e:
        print(f"목록 가져오기 실패: {e}")
        return

    exam_links = []
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if href.startswith('/exam/') and href not in [link['href'] for link in exam_links]:
            title = a.text.strip()
            if not title:
                continue
            exam_links.append({'title': title, 'href': href})
            
    print(f"총 {len(exam_links)}개의 기출문제를 찾았습니다.")
    
    os.makedirs('anchor_data', exist_ok=True)
    
    count = 0
    for exam in exam_links:
        exam_id = exam['href'].split('/')[-1]
        filepath = f"anchor_data/cbtbank_{exam_id}.txt"
        
        if os.path.exists(filepath):
            print(f"이미 존재함: {filepath}")
            continue
            
        exam_url = f"{base_url}{exam['href']}"
        print(f"수집 중: {exam_url}")
        try:
            er = requests.get(exam_url, headers=headers)
            er.raise_for_status()
            esoup = BeautifulSoup(er.content, 'html.parser')
            
            for script in esoup(["script", "style", "nav", "footer", "header"]):
                script.extract()
                
            text = esoup.get_text(separator='\n')
            
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = "\n".join(lines)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Source: {exam_url}\n")
                f.write(f"Title: {exam['title']}\n\n")
                f.write(clean_text)
                
            count += 1
            time.sleep(1.5) 
        except Exception as e:
            print(f"수집 실패 ({exam_url}): {e}")
            
    print(f"\n총 {count}개의 기출문제를 성공적으로 스크래핑하여 anchor_data/ 폴더에 저장했습니다!")

if __name__ == "__main__":
    scrape_cbtbank()
