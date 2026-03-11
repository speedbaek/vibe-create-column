import requests
import json
from datetime import datetime
import time
import os
from bs4 import BeautifulSoup

def fetch_post_list(blog_id, page):
    url = f"https://m.blog.naver.com/api/blogs/{blog_id}/post-list?categoryNo=0&itemCount=30&page={page}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)',
        'Referer': f'https://m.blog.naver.com/{blog_id}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        text = response.text
        if text.startswith(")]}',"):
            text = text[5:]
        try:
            return json.loads(text)
        except Exception:
            return None
    return None

def fetch_post_content(blog_id, log_no):
    url = f"https://m.blog.naver.com/{blog_id}/{log_no}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        # Naver mobile blog text is usually inside .se-main-container
        content_div = soup.find('div', class_='se-main-container')
        if content_div:
            return content_div.get_text(separator='\n', strip=True)
        # Fallback for old layouts
        fallback = soup.find('div', id='viewTypeSelector')
        if fallback:
            return fallback.get_text(separator='\n', strip=True)
    return "본문을 불러올 수 없습니다."

def run_scraper(persona_id, blog_id, start_date_str, end_date_str, progress_callback=None):
    start_date = datetime.strptime(start_date_str.replace("-", ""), "%Y%m%d")
    end_date = datetime.strptime(end_date_str.replace("-", ""), "%Y%m%d")
    
    page = 1
    found_posts = []
    
    if progress_callback:
        progress_callback(f"블로그({blog_id})에서 {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} 기간의 글을 검색합니다...\n", 10)
        
    while True:
        data = fetch_post_list(blog_id, page)
        if not data or not data.get('isSuccess'):
            break
            
        items = data.get('result', {}).get('items', [])
        if not items:
            break
            
        should_continue = True
        for item in items:
            log_no = item.get('logNo')
            title = item.get('titleWithInspectMessage')
            add_date = item.get('addDate') 
            
            if not add_date:
                continue
                
            post_date = datetime.fromtimestamp(add_date / 1000.0)
            
            if post_date > end_date:
                continue
            elif post_date < start_date:
                should_continue = False
                break
            else:
                if progress_callback:
                    progress_callback(f"[발견] {title} ({post_date.strftime('%Y-%m-%d')}) 추출 중...\n", 30)
                
                # Fetch the actual post content
                content_text = fetch_post_content(blog_id, log_no)
                
                found_posts.append({
                    'logNo': log_no,
                    'title': title,
                    'date': post_date.strftime('%Y-%m-%d'),
                    'content': content_text
                })
                time.sleep(1) # Be polite to Naver
                
        if not should_continue:
            break
            
        page += 1
        time.sleep(0.5)
        
    if progress_callback:
        progress_callback(f"총 {len(found_posts)}개의 글을 성공적으로 수집했습니다. DB에 병합합니다...\n", 90)
    
    # Save the scraped posts to the persona's blogs.json
    db_dir = f"persona_db/{persona_id}"
    os.makedirs(db_dir, exist_ok=True)
    
    blogs_path = os.path.join(db_dir, "blogs.json")
    existing_posts = []
    
    if os.path.exists(blogs_path):
        try:
            with open(blogs_path, 'r', encoding='utf-8') as f:
                existing_posts = json.load(f)
        except Exception:
            pass
            
    # Combine and ensure unique logs
    existing_logs = {str(p.get('logNo', '')) for p in existing_posts}
    for new_post in found_posts:
        if str(new_post['logNo']) not in existing_logs:
            existing_posts.insert(0, new_post)
            
    with open(blogs_path, 'w', encoding='utf-8') as f:
        json.dump(existing_posts, f, ensure_ascii=False, indent=4)
        
    if progress_callback:
        progress_callback(f"저장 완료! 기존 글 포함 총 {len(existing_posts)}개의 데이터가 DB에 있습니다.\n", 100)
    
    return len(found_posts)
