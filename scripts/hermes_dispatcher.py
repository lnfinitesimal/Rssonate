import os
import json
import time
import feedparser
from groq import Groq

# Shard logic: Map regions to RSS feeds
FEEDS = {
    "americas": ["http://rss.cnn.com/rss/edition_us.rss", "https://feeds.a.dj.com/rss/RSSWorldNews.xml"],
    "emea": ["http://rss.cnn.com/rss/edition_europe.rss", "http://feeds.bbci.co.uk/news/rss.xml"],
    "apac": ["http://rss.cnn.com/rss/edition_asia.rss", "https://www.aljazeera.com/xml/rss/all.xml"]
}

region = os.environ.get("REGION_SHARD", "americas")
urls = FEEDS.get(region, [])

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
OUT_DIR = "public"

def classify_article(title, snippet):
    prompt = f"""
    Categorize this news article into a strict hierarchy: Category > Topic > Leaf.
    Example output: ["sports", "football", "premier_league"]
    Example output: ["technology", "artificial_intelligence", "openai"]
    
    Article: {title}
    Snippet: {snippet}
    
    Return ONLY a valid JSON array of 3 lowercase strings. No markdown.
    """
    try:
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=50
        )
        result = completion.choices[0].message.content.strip()
        return json.loads(result)
    except Exception as e:
        print(f"Classification failed: {e}")
        return ["world", "general", "news"]

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    
    for url in urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:20]: # Process top 20 per feed to stay under 2h limit
            title = entry.get("title", "")
            link = entry.get("link", "")
            snippet = entry.get("summary", "")[:300]
            timestamp = int(time.time() * 1000)
            
            # Rate limit protection for Groq free tier
            time.sleep(1.5) 
            
            path_array = classify_article(title, snippet)
            if len(path_array) != 3: continue
            
            # Build directory path: public/sports/football
            cat, topic, leaf = path_array
            target_dir = os.path.join(OUT_DIR, cat, topic)
            os.makedirs(target_dir, exist_ok=True)
            
            # The JSON file your Android app downloads: public/sports/football/premier_league.json
            file_path = os.path.join(target_dir, f"{leaf}.json")
            
            # Load existing or create new
            articles = []
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    articles = json.load(f)
            
            # Prevent duplicates
            if not any(a["url"] == link for a in articles):
                articles.insert(0, {
                    "url": link,
                    "title": title,
                    "snippet": snippet,
                    "imageUrl": None,
                    "timestamp": timestamp
                })
            
            # 24-HOUR ROLLING WIPE: Keep only articles from the last 86400000 ms
            cutoff = timestamp - 86400000
            articles = [a for a in articles if a["timestamp"] > cutoff]
            
            # Write back
            with open(file_path, "w") as f:
                json.dump(articles, f)

if __name__ == "__main__":
    main()
