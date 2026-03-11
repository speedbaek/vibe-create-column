import requests
import json
from bs4 import BeautifulSoup
import time
import os

blog_id = 'jninsa'

def get_post_content(log_no):
    # For content, it's easier to scrape the mobile web version
    url = f"https://m.blog.naver.com/{blog_id}/{log_no}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        
        # In Naver mobile blog, the main text is usually under a specific structural div
        # typically components like se-main-container or postViewArea
        content_div = soup.find('div', class_='se-main-container')
        
        if content_div:
            # Extract text, removing excessive newlines
            text = content_div.get_text(separator='\n\n', strip=True)
            return text
        else:
            # Fallback for older editor formats
            content_div = soup.find('div', id='postViewArea')
            if content_div:
                 return content_div.get_text(separator='\n\n', strip=True)
            else:
                 # Generic fallback
                 main_content = soup.find('div', class_='__se_component_area')
                 if main_content:
                     return main_content.get_text(separator='\n\n', strip=True)
                 return ""
    except Exception as e:
        print(f"Error fetching {log_no}: {e}")
        return ""

def main():
    if not os.path.exists('target_posts.json'):
        print("target_posts.json not found. Run scraper.py first.")
        return
        
    with open('target_posts.json', 'r', encoding='utf-8') as f:
        posts = json.load(f)
        
    print(f"Loaded {len(posts)} posts. Starting content extraction...")
    
    output_dir = "data/raw_texts"
    os.makedirs(output_dir, exist_ok=True)
    
    all_texts = []
    
    # Process all posts
    print(f"Extracting all {len(posts)} posts...")
    
    for i, post in enumerate(posts):
        log_no = post['logNo']
        title = post['title']
        date = post['date']
        
        print(f"[{i+1}/{len(posts)}] Fetching: {title}")
        content = get_post_content(log_no)
        
        if content:
            # Write individual file
            filename = f"{output_dir}/{date}_{log_no}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Title: {title}\nDate: {date}\n\n{content}")
                
            all_texts.append({
                'title': title,
                'date': date,
                'content': content
            })
        else:
            print(f"   -> Failed to extract content.")
            
        time.sleep(1) # Polite delay
        
    # Save compilation
    with open('data/all_texts_compiled.json', 'w', encoding='utf-8') as f:
        json.dump(all_texts, f, ensure_ascii=False, indent=4)
        
    print(f"\nExtraction complete. {len(all_texts)} posts saved in data/raw_texts/ and data/all_texts_compiled.json")

if __name__ == "__main__":
    main()
