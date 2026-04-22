"""
╔══════════════════════════════════════════════════════════════╗
║   WAR IMPACT COMMODITY ANALYZER (INDIA)                      ║
║   Flask Backend — Full-featured dashboard                    ║
║   Prices in ₹ INR | ML Prediction | Alerts | War News       ║
╚══════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
import sqlite3, os, json, time, math, threading, random
from collections import deque
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# in-memory live price snapshots for dynamic refresh
LIVE_PRICE_DATASETS = deque(maxlen=200)

# ── Optional ML import (graceful fallback) ───────────────────
try:
    from models.predictor import predict_next_prices
    ML_AVAILABLE = True
except Exception:
    ML_AVAILABLE = False

# ── User Model ─────────────────
class User(UserMixin):
    def __init__(self, id, username, email, password_hash, is_admin=False, oauth_provider=None, oauth_id=None):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.oauth_provider = oauth_provider
        self.oauth_id = oauth_id

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, password_hash, is_admin, oauth_provider, oauth_id FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return User(row['id'], row['username'], row['email'], row['password_hash'], 
                   row['is_admin'], row['oauth_provider'], row['oauth_id'])
    return None

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

# ══════════════════════════════════════════════════════════════
#  USD → INR  (cached 20 min, fallback ₹84)
# ══════════════════════════════════════════════════════════════

_rate_cache = {"rate": 84.0, "fetched_at": 0}
_RATE_TTL   = 20 * 60

def get_usd_inr_rate() -> float:
    now = time.time()
    if now - _rate_cache["fetched_at"] < _RATE_TTL:
        return _rate_cache["rate"]
    try:
        import urllib.request as ur
        urls = [
            "https://open.er-api.com/v6/latest/USD",
            "https://api.exchangerate-api.com/v4/latest/USD",
        ]
        for url in urls:
            try:
                req = ur.Request(url, headers={"User-Agent": "war-analyzer/2.0"})
                with ur.urlopen(req, timeout=5) as r:
                    data = json.loads(r.read().decode())
                rate = float(data["rates"]["INR"])
                _rate_cache.update({"rate": rate, "fetched_at": now})
                print(f"💱 USD→INR refreshed: ₹{rate:.2f}")
                return rate
            except Exception as e:
                print(f"⚠️  Rate API failed: {e}")
    except Exception:
        pass
    return _rate_cache["rate"]

# ══════════════════════════════════════════════════════════════
#  REAL-TIME COMMODITY PRICES
# ══════════════════════════════════════════════════════════════

# Cache for commodity prices (3 minute TTL for faster real-time updates in production)
_commodity_cache = {}
_COMMODITY_TTL = 3 * 60

def get_real_time_commodity_prices():
    """Fetch real-time prices for commodities using multiple APIs with fallbacks."""
    now = time.time()
    
    # Return cached data if still fresh
    if _commodity_cache and now - _commodity_cache.get("fetched_at", 0) < _COMMODITY_TTL:
        return _commodity_cache["prices"]
    
    prices = {}
    
    # Alpha Vantage API (primary source for international commodities)
    alpha_vantage_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if alpha_vantage_key:
        try:
            # Crude Oil (WTI)
            response = requests.get(f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=CL&apikey={alpha_vantage_key}', timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'Global Quote' in data and data['Global Quote'].get('05. price'):
                    prices['Crude Oil'] = float(data['Global Quote']['05. price'])
                    print(f"🛢️  Crude Oil: ${prices['Crude Oil']:.2f}")
            
            # Gold
            response = requests.get(f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=GC&apikey={alpha_vantage_key}', timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'Global Quote' in data and data['Global Quote'].get('05. price'):
                    prices['Gold'] = float(data['Global Quote']['05. price'])
                    print(f"🥇 Gold: ${prices['Gold']:.2f}")
            
            # Silver
            response = requests.get(f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SI&apikey={alpha_vantage_key}', timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'Global Quote' in data and data['Global Quote'].get('05. price'):
                    prices['Silver'] = float(data['Global Quote']['05. price'])
                    print(f"🥈 Silver: ${prices['Silver']:.2f}")
            
            # Natural Gas
            response = requests.get(f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=NG&apikey={alpha_vantage_key}', timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'Global Quote' in data and data['Global Quote'].get('05. price'):
                    prices['Natural Gas'] = float(data['Global Quote']['05. price'])
                    print(f"🔥 Natural Gas: ${prices['Natural Gas']:.2f}")
                    
        except Exception as e:
            print(f"⚠️  Alpha Vantage API failed: {e}")
    
    # Fallback: Yahoo Finance API for additional data
    try:
        # Yahoo Finance for commodities
        yahoo_symbols = {
            'Crude Oil': 'CL=F',
            'Gold': 'GC=F', 
            'Silver': 'SI=F',
            'Natural Gas': 'NG=F'
        }
        
        for commodity, symbol in yahoo_symbols.items():
            if commodity not in prices:  # Only fetch if not already fetched from Alpha Vantage
                try:
                    response = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d', 
                                          headers={'User-Agent': 'war-analyzer/2.0'}, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                            price_data = data['chart']['result'][0]
                            if 'meta' in price_data and 'regularMarketPrice' in price_data['meta']:
                                prices[commodity] = float(price_data['meta']['regularMarketPrice'])
                                print(f"📊 {commodity} (Yahoo): ${prices[commodity]:.2f}")
                except Exception as e:
                    print(f"⚠️  Yahoo Finance failed for {commodity}: {e}")
                    
    except Exception as e:
        print(f"⚠️  Yahoo Finance API failed: {e}")
    
    # Fallback: Web scraping from reliable sources
    try:
        # Investing.com for commodities
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        # For Indian commodities (Petrol, Diesel, etc.), we might need different sources
        # For now, let's use some static adjustments or web scraping
        
        # Example: Try to get current petrol/diesel prices from a reliable source
        # This is a simplified example - in production you'd want more robust scraping
        
        # For demonstration, we'll use some base prices with small random variations
        # In a real implementation, you'd integrate with Indian fuel price APIs
        
    except Exception as e:
        print(f"⚠️  Web scraping failed: {e}")
    
    # Update cache
    _commodity_cache["prices"] = prices
    _commodity_cache["fetched_at"] = now
    
    if prices:
        print(f"📈 Updated {len(prices)} commodity prices at {datetime.now().strftime('%H:%M:%S')}")
    
    return prices

# ══════════════════════════════════════════════════════════════
#  REAL-TIME WAR NEWS
# ══════════════════════════════════════════════════════════════

# Cache for news (10 minute TTL for more real-time feel)
_news_cache = {"news": [], "fetched_at": 0}
_NEWS_TTL = 10 * 60

def fetch_real_time_war_news():
    """Fetch real-time war and conflict news from multiple sources."""
    now = time.time()

    # Return cached news if still fresh
    if _news_cache["news"] and now - _news_cache["fetched_at"] < _NEWS_TTL:
        return _news_cache["news"]

    all_news = []

    # NewsAPI (Primary source)
    news_api_key = os.environ.get('NEWS_API_KEY', '')
    if news_api_key:
        try:
            # Search for war/conflict related news with better keywords
            war_queries = [
                "war OR conflict OR military OR invasion OR attack OR bombing",
                '"Ukraine Russia" OR "Russia Ukraine" OR Putin OR Zelensky',
                '"Israel Hamas" OR "Iran Israel" OR Gaza OR Hezbollah',
                "Middle East conflict OR geopolitical OR sanctions OR ceasefire"
            ]

            for query in war_queries[:2]:  # Limit to avoid rate limits
                try:
                    url = f"https://newsapi.org/v2/everything?q={query}&language=en&sortBy=publishedAt&pageSize=5&apiKey={news_api_key}"
                    response = requests.get(url, timeout=15)

                    if response.status_code == 200:
                        data = response.json()
                        if data.get('articles'):
                            for article in data['articles'][:2]:  # Limit articles per query
                                if article.get('title') and article.get('description'):
                                    news_item = {
                                        'title': article['title'],
                                        'description': article['description'][:250] + '...' if len(article['description']) > 250 else article['description'],
                                        'source': article['source'].get('name', 'NewsAPI'),
                                        'url': article.get('url', ''),
                                        'published_at': article.get('publishedAt', datetime.now().isoformat()),
                                        'conflict': classify_conflict(article['title'] + ' ' + article['description'])
                                    }
                                    all_news.append(news_item)
                except Exception as e:
                    print(f"⚠️  NewsAPI failed for query '{query[:30]}...': {e}")

        except Exception as e:
            print(f"⚠️  NewsAPI failed: {e}")

    # Enhanced RSS feeds with better parsing
    try:
        import feedparser
        rss_sources = [
            {
                'name': 'BBC News',
                'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',
                'parser': 'feedparser'
            },
            {
                'name': 'Reuters',
                'url': 'https://feeds.reuters.com/Reuters/worldNews',
                'parser': 'feedparser'
            },
            {
                'name': 'Al Jazeera',
                'url': 'https://www.aljazeera.com/xml/rss/all.xml',
                'parser': 'feedparser'
            },
            {
                'name': 'CNN',
                'url': 'http://rss.cnn.com/rss/edition_world.rss',
                'parser': 'feedparser'
            },
            {
                'name': 'The Guardian',
                'url': 'https://www.theguardian.com/world/rss',
                'parser': 'feedparser'
            }
        ]

        for source in rss_sources:
            try:
                if source['parser'] == 'feedparser':
                    feed = feedparser.parse(source['url'])
                    if feed.entries:
                        for entry in feed.entries[:3]:  # Get more articles per source
                            title = entry.get('title', '').strip()
                            description = entry.get('summary', entry.get('description', '')).strip()

                            if title and description:
                                # Check if it's war-related
                                war_indicators = [
                                    'war', 'conflict', 'military', 'attack', 'invasion', 'bomb',
                                    'missile', 'sanction', 'ceasefire', 'peace talks', 'geopolitical',
                                    'ukraine', 'russia', 'israel', 'hamas', 'iran', 'gaza', 'hezbollah'
                                ]
                                content_text = (title + ' ' + description).lower()

                                if any(indicator in content_text for indicator in war_indicators):
                                    news_item = {
                                        'title': title[:100] + '...' if len(title) > 100 else title,
                                        'description': description[:250] + '...' if len(description) > 250 else description,
                                        'source': source['name'],
                                        'url': entry.get('link', ''),
                                        'published_at': entry.get('published', datetime.now().isoformat()),
                                        'conflict': classify_conflict(title + ' ' + description)
                                    }
                                    all_news.append(news_item)
                else:
                    # Fallback XML parsing
                    response = requests.get(source['url'], timeout=10, headers={'User-Agent': 'war-analyzer/2.0'})
                    if response.status_code == 200:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(response.content)

                        for item in root.findall('.//item')[:2]:
                            title_elem = item.find('title')
                            desc_elem = item.find('description')
                            link_elem = item.find('link')
                            pub_elem = item.find('pubDate')

                            if title_elem is not None and desc_elem is not None:
                                title = title_elem.text
                                description = desc_elem.text

                                war_indicators = ['war', 'conflict', 'military', 'attack', 'invasion', 'bomb', 'missile', 'sanction']
                                content_text = (title + ' ' + description).lower()

                                if any(indicator in content_text for indicator in war_indicators):
                                    news_item = {
                                        'title': title[:100] + '...' if len(title) > 100 else title,
                                        'description': description[:200] + '...' if len(description) > 200 else description,
                                        'source': source['name'],
                                        'url': link_elem.text if link_elem is not None else '',
                                        'published_at': pub_elem.text if pub_elem is not None else datetime.now().isoformat(),
                                        'conflict': classify_conflict(title + ' ' + description)
                                    }
                                    all_news.append(news_item)

            except Exception as e:
                print(f"⚠️  RSS feed failed for {source['name']}: {e}")

    except ImportError:
        print("⚠️  feedparser not installed, using basic RSS parsing")
        # Fallback to basic RSS parsing if feedparser not available
        try:
            rss_sources = [
                {'name': 'BBC News', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml'},
                {'name': 'Reuters', 'url': 'https://feeds.reuters.com/Reuters/worldNews'}
            ]

            for source in rss_sources:
                try:
                    response = requests.get(source['url'], timeout=10, headers={'User-Agent': 'war-analyzer/2.0'})
                    if response.status_code == 200:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(response.content)

                        for item in root.findall('.//item')[:2]:
                            title_elem = item.find('title')
                            desc_elem = item.find('description')
                            link_elem = item.find('link')
                            pub_elem = item.find('pubDate')

                            if title_elem is not None and desc_elem is not None:
                                title = title_elem.text
                                description = desc_elem.text

                                war_indicators = ['war', 'conflict', 'military', 'attack', 'invasion', 'bomb', 'missile', 'sanction']
                                content_text = (title + ' ' + description).lower()

                                if any(indicator in content_text for indicator in war_indicators):
                                    news_item = {
                                        'title': title[:100] + '...' if len(title) > 100 else title,
                                        'description': description[:200] + '...' if len(description) > 200 else description,
                                        'source': source['name'],
                                        'url': link_elem.text if link_elem is not None else '',
                                        'published_at': pub_elem.text if pub_elem is not None else datetime.now().isoformat(),
                                        'conflict': classify_conflict(title + ' ' + description)
                                    }
                                    all_news.append(news_item)

                except Exception as e:
                    print(f"⚠️  RSS feed failed for {source['name']}: {e}")
        except Exception as e:
            print(f"⚠️  RSS parsing failed: {e}")

    # Additional fallback: Google News RSS (if available)
    try:
        google_news_urls = [
            'https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=en-IN&gl=IN&ceid=IN:en',
            'https://news.google.com/rss/search?q=war+OR+conflict+OR+military+OR+invasion&hl=en-IN&gl=IN&ceid=IN:en'
        ]

        for url in google_news_urls[:1]:  # Limit to one Google News feed
            try:
                response = requests.get(url, timeout=10, headers={'User-Agent': 'war-analyzer/2.0'})
                if response.status_code == 200:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(response.content)

                    for item in root.findall('.//item')[:3]:
                        title_elem = item.find('title')
                        desc_elem = item.find('description')
                        link_elem = item.find('link')
                        pub_elem = item.find('pubDate')

                        if title_elem is not None:
                            title = title_elem.text
                            description = desc_elem.text if desc_elem is not None else title

                            war_indicators = ['war', 'conflict', 'military', 'attack', 'invasion', 'bomb', 'missile', 'sanction']
                            content_text = (title + ' ' + description).lower()

                            if any(indicator in content_text for indicator in war_indicators):
                                news_item = {
                                    'title': title[:100] + '...' if len(title) > 100 else title,
                                    'description': description[:200] + '...' if len(description) > 200 else description,
                                    'source': 'Google News',
                                    'url': link_elem.text if link_elem is not None else '',
                                    'published_at': pub_elem.text if pub_elem is not None else datetime.now().isoformat(),
                                    'conflict': classify_conflict(title + ' ' + description)
                                }
                                all_news.append(news_item)

            except Exception as e:
                print(f"⚠️  Google News RSS failed: {e}")

    except Exception as e:
        print(f"⚠️  Google News parsing failed: {e}")

    # Remove duplicates and sort by date
    seen_titles = set()
    unique_news = []

    for news in all_news:
        title_key = news['title'].lower()[:50]  # First 50 chars as uniqueness key
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_news.append(news)

    # Sort by published date (newest first)
    unique_news.sort(key=lambda x: x.get('published_at', ''), reverse=True)

    # Limit to 100 most recent articles
    final_news = unique_news[:100]

    # Update cache
    _news_cache["news"] = final_news
    _news_cache["fetched_at"] = now

    if final_news:
        print(f"📰 Fetched {len(final_news)} war news articles from {len(set(n['source'] for n in final_news))} sources at {datetime.now().strftime('%H:%M:%S')}")

    return final_news

def classify_conflict(text):
    """Classify news into conflict categories."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['ukraine', 'russia', 'putin', 'zelensky', 'kyiv', 'moscow']):
        return 'Russia-Ukraine'
    elif any(word in text_lower for word in ['israel', 'palestine', 'hamas', 'gaza', 'iran', 'hezbollah', 'idf']):
        return 'Iran-Israel-USA'
    elif any(word in text_lower for word in ['china', 'taiwan', 'south china sea']):
        return 'China-Taiwan'
    elif any(word in text_lower for word in ['india', 'pakistan', 'kashmir']):
        return 'India-Pakistan'
    else:
        return 'General'

def update_database_with_news():
    """Update the database with fresh news articles."""
    try:
        fresh_news = fetch_real_time_war_news()
        if not fresh_news:
            return
        
        conn = get_db()
        cur = conn.cursor()
        
        # Clear old news (keep only last 7 days)
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        cur.execute("DELETE FROM news WHERE date < ?", (seven_days_ago,))
        
        # Insert new news (avoid duplicates)
        inserted_count = 0
        for news_item in fresh_news:
            try:
                # Check if news already exists
                cur.execute("SELECT id FROM news WHERE title = ? AND source = ?", 
                           (news_item['title'], news_item['source']))
                
                if not cur.fetchone():
                    # Parse published date
                    try:
                        published_date = datetime.fromisoformat(news_item['published_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    except:
                        published_date = datetime.now().strftime('%Y-%m-%d')
                    
                    cur.execute("""
                        INSERT INTO news (title, description, date, source, conflict) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        news_item['title'],
                        news_item['description'],
                        published_date,
                        news_item['source'],
                        news_item['conflict']
                    ))
                    inserted_count += 1
                    
            except Exception as e:
                print(f"⚠️  Failed to insert news '{news_item['title'][:30]}...': {e}")
        
        conn.commit()
        conn.close()
        
        if inserted_count > 0:
            print(f"📝 Added {inserted_count} new war news articles to database")
            
    except Exception as e:
        print(f"⚠️  News database update failed: {e}")

# ══════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cur  = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email    TEXT UNIQUE,
            password_hash TEXT,
            is_admin INTEGER DEFAULT 0,
            oauth_provider TEXT,
            oauth_id TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS commodities (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            unit     TEXT NOT NULL DEFAULT 'USD',
            symbol   TEXT NOT NULL DEFAULT '📦'
        );

        CREATE TABLE IF NOT EXISTS prices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            commodity_id INTEGER NOT NULL REFERENCES commodities(id),
            price        REAL    NOT NULL,
            date         TEXT    NOT NULL,
            UNIQUE(commodity_id, date)
        );

        CREATE TABLE IF NOT EXISTS war_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name  TEXT NOT NULL,
            date        TEXT NOT NULL,
            description TEXT,
            conflict    TEXT DEFAULT 'Russia-Ukraine',
            impact      TEXT DEFAULT 'medium'
        );

        CREATE TABLE IF NOT EXISTS news (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT,
            date        TEXT NOT NULL,
            source      TEXT DEFAULT 'Simulated',
            conflict    TEXT DEFAULT 'General'
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            commodity_id INTEGER NOT NULL REFERENCES commodities(id),
            threshold    REAL NOT NULL,
            direction    TEXT NOT NULL DEFAULT 'above',
            active       INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL
        );
    """)

    # ── Commodities ────────────────────────────────────────────
    commodities = [
        ("Crude Oil",     "Energy",          "USD/Barrel",  "🛢️"),
        ("Petrol",        "Energy",          "INR/Litre",   "⛽"),
        ("Diesel",        "Energy",          "INR/Litre",   "🚛"),
        ("Gold",          "Precious Metals", "USD/Oz",      "🥇"),
        ("Silver",        "Precious Metals", "USD/Oz",      "🥈"),
        ("Wheat",         "Agriculture",     "INR/Quintal", "🌾"),
        ("Rice",          "Agriculture",     "INR/Quintal", "🍚"),
        ("Edible Oil",    "Agriculture",     "INR/Litre",   "🫙"),
        ("Natural Gas",   "Energy",          "USD/MMBtu",   "🔥"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO commodities (name, category, unit, symbol) VALUES (?,?,?,?)",
        commodities
    )

    # ── Price history (Jan 2021 – Jan 2025) ────────────────────
    prices = [
        # Crude Oil (USD/Barrel)
        (1,55.0,"2021-01"),(1,59.0,"2021-04"),(1,73.0,"2021-07"),
        (1,83.0,"2021-10"),(1,85.0,"2022-01"),(1,95.0,"2022-02"),
        (1,110.0,"2022-03"),(1,105.0,"2022-04"),(1,100.0,"2022-07"),
        (1,92.0,"2022-10"),(1,80.0,"2023-01"),(1,78.0,"2023-04"),
        (1,82.0,"2023-07"),(1,88.0,"2023-10"),(1,78.0,"2024-01"),
        (1,83.0,"2024-04"),(1,82.0,"2024-07"),(1,75.0,"2024-10"),
        (1,72.5,"2025-01"),

        # Petrol INR/Litre
        (2,88.0,"2021-01"),(2,90.5,"2021-04"),(2,96.7,"2021-07"),
        (2,102.8,"2021-10"),(2,105.5,"2022-01"),(2,107.2,"2022-02"),
        (2,112.0,"2022-03"),(2,110.5,"2022-04"),(2,106.3,"2022-07"),
        (2,104.8,"2022-10"),(2,103.0,"2023-01"),(2,102.3,"2023-04"),
        (2,101.7,"2023-07"),(2,102.5,"2023-10"),(2,101.0,"2024-01"),
        (2,103.4,"2024-04"),(2,104.2,"2024-07"),(2,103.8,"2024-10"),
        (2,102.9,"2025-01"),

        # Diesel INR/Litre
        (3,78.5,"2021-01"),(3,80.0,"2021-04"),(3,89.6,"2021-07"),
        (3,93.7,"2021-10"),(3,95.0,"2022-01"),(3,96.2,"2022-02"),
        (3,100.0,"2022-03"),(3,98.5,"2022-04"),(3,95.7,"2022-07"),
        (3,93.1,"2022-10"),(3,91.5,"2023-01"),(3,90.8,"2023-04"),
        (3,90.2,"2023-07"),(3,91.0,"2023-10"),(3,89.5,"2024-01"),
        (3,91.3,"2024-04"),(3,92.0,"2024-07"),(3,91.6,"2024-10"),
        (3,90.7,"2025-01"),

        # Gold (USD/Oz)
        (4,1850.0,"2021-01"),(4,1780.0,"2021-04"),(4,1800.0,"2021-07"),
        (4,1780.0,"2021-10"),(4,1820.0,"2022-01"),(4,1900.0,"2022-02"),
        (4,1950.0,"2022-03"),(4,1940.0,"2022-04"),(4,1760.0,"2022-07"),
        (4,1650.0,"2022-10"),(4,1920.0,"2023-01"),(4,2000.0,"2023-04"),
        (4,1950.0,"2023-07"),(4,1930.0,"2023-10"),(4,2050.0,"2024-01"),
        (4,2280.0,"2024-04"),(4,2410.0,"2024-07"),(4,2650.0,"2024-10"),
        (4,2830.0,"2025-01"),

        # Silver (USD/Oz)
        (5,25.5,"2021-01"),(5,24.8,"2021-04"),(5,26.0,"2021-07"),
        (5,23.8,"2021-10"),(5,24.2,"2022-01"),(5,24.8,"2022-02"),
        (5,25.5,"2022-03"),(5,24.9,"2022-04"),(5,19.5,"2022-07"),
        (5,18.8,"2022-10"),(5,24.0,"2023-01"),(5,25.5,"2023-04"),
        (5,23.0,"2023-07"),(5,22.0,"2023-10"),(5,23.5,"2024-01"),
        (5,27.0,"2024-04"),(5,29.0,"2024-07"),(5,32.0,"2024-10"),
        (5,30.5,"2025-01"),

        # Wheat (INR/Quintal)
        (6,2200.0,"2021-01"),(6,2150.0,"2021-04"),(6,2350.0,"2021-07"),
        (6,2450.0,"2021-10"),(6,2550.0,"2022-01"),(6,2900.0,"2022-02"),
        (6,3800.0,"2022-03"),(6,3700.0,"2022-04"),(6,3200.0,"2022-07"),
        (6,3000.0,"2022-10"),(6,2850.0,"2023-01"),(6,2750.0,"2023-04"),
        (6,2700.0,"2023-07"),(6,2650.0,"2023-10"),(6,2550.0,"2024-01"),
        (6,2600.0,"2024-04"),(6,2650.0,"2024-07"),(6,2700.0,"2024-10"),
        (6,2750.0,"2025-01"),

        # Rice (INR/Quintal)
        (7,1850.0,"2021-01"),(7,1900.0,"2021-04"),(7,1920.0,"2021-07"),
        (7,1960.0,"2021-10"),(7,2000.0,"2022-01"),(7,2050.0,"2022-02"),
        (7,2100.0,"2022-03"),(7,2080.0,"2022-04"),(7,2050.0,"2022-07"),
        (7,2100.0,"2022-10"),(7,2150.0,"2023-01"),(7,2200.0,"2023-04"),
        (7,2450.0,"2023-07"),(7,2700.0,"2023-10"),(7,2750.0,"2024-01"),
        (7,2800.0,"2024-04"),(7,2820.0,"2024-07"),(7,2800.0,"2024-10"),
        (7,2750.0,"2025-01"),

        # Edible Oil (INR/Litre)
        (8,120.0,"2021-01"),(8,130.0,"2021-04"),(8,145.0,"2021-07"),
        (8,155.0,"2021-10"),(8,160.0,"2022-01"),(8,175.0,"2022-02"),
        (8,195.0,"2022-03"),(8,190.0,"2022-04"),(8,170.0,"2022-07"),
        (8,155.0,"2022-10"),(8,145.0,"2023-01"),(8,140.0,"2023-04"),
        (8,135.0,"2023-07"),(8,130.0,"2023-10"),(8,128.0,"2024-01"),
        (8,132.0,"2024-04"),(8,135.0,"2024-07"),(8,138.0,"2024-10"),
        (8,140.0,"2025-01"),

        # Natural Gas (USD/MMBtu)
        (9,2.7,"2021-01"),(9,2.6,"2021-04"),(9,3.8,"2021-07"),
        (9,5.5,"2021-10"),(9,4.5,"2022-01"),(9,4.8,"2022-02"),
        (9,4.9,"2022-03"),(9,6.6,"2022-04"),(9,8.2,"2022-07"),
        (9,6.0,"2022-10"),(9,3.4,"2023-01"),(9,2.2,"2023-04"),
        (9,2.6,"2023-07"),(9,3.1,"2023-10"),(9,2.8,"2024-01"),
        (9,1.9,"2024-04"),(9,2.2,"2024-07"),(9,2.9,"2024-10"),
        (9,3.5,"2025-01"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO prices (commodity_id, price, date) VALUES (?,?,?)",
        prices
    )

    # ── War Events ─────────────────────────────────────────────
    events = [
        ("Russia Begins Ukraine Invasion", "2022-02-24",
         "Full-scale invasion triggers immediate global commodity shock across energy, wheat, and metals.",
         "Russia-Ukraine", "high"),
        ("Western Sanctions on Russian Oil", "2022-04-08",
         "G7 + EU sanctions on Russian crude disrupt global supply chains and push oil above $110/barrel.",
         "Russia-Ukraine", "high"),
        ("Ukraine Black Sea Grain Deal", "2022-07-22",
         "UN-brokered deal reopens Ukrainian ports — wheat futures fall 8% on news.",
         "Russia-Ukraine", "medium"),
        ("Russia Suspends Grain Agreement", "2023-07-17",
         "Russia withdraws from grain corridor deal, wheat surges 8% in a single session.",
         "Russia-Ukraine", "high"),
        ("Hamas Attack on Israel", "2023-10-07",
         "Major escalation in Middle East injects sharp uncertainty into oil futures; Brent rises $4.",
         "Iran-Israel-USA", "high"),
        ("Red Sea Houthi Attacks Begin", "2024-01-12",
         "Iran-backed Houthi attacks on Red Sea shipping raise freight costs and oil insurance premiums.",
         "Iran-Israel-USA", "medium"),
        ("Iran Direct Missile Strike on Israel", "2024-04-13",
         "First-ever direct Iranian strike on Israeli territory sends crude to 6-month high above $92.",
         "Iran-Israel-USA", "high"),
        ("US Airstrikes on Iran-backed Forces", "2024-02-02",
         "Pentagon strikes 85 targets in Syria and Iraq after Jordan drone attack on US base.",
         "Iran-Israel-USA", "medium"),
        ("India Bans Wheat Exports", "2022-05-14",
         "India bans wheat exports to control domestic inflation — global prices spike as supply tightens.",
         "Russia-Ukraine", "medium"),
        ("Russia Cuts Gas Supply to Europe", "2022-08-31",
         "Gazprom halts Nord Stream 1 gas flows indefinitely. European natural gas hits record €350/MWh.",
         "Russia-Ukraine", "high"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO war_events (event_name, date, description, conflict, impact) VALUES (?,?,?,?,?)",
        events
    )

    # ── News ───────────────────────────────────────────────────
    news_items = [
        ("Russia-Ukraine War: Grain Corridor Collapses",
         "The UN-brokered Black Sea Grain Initiative has officially ended after Russia refused renewal, threatening global food security.",
         "2023-07-18", "Reuters", "Russia-Ukraine"),
        ("Oil Prices Spike After Iran-Israel Confrontation",
         "Brent crude surged above $92/barrel following Iran's unprecedented direct missile strike on Israel, marking a historic escalation.",
         "2024-04-14", "Bloomberg", "Iran-Israel-USA"),
        ("Houthi Attacks Force Ships Away From Red Sea",
         "Major shipping companies diverting routes around Cape of Good Hope, adding 10-14 days and up to $1M in fuel costs per voyage.",
         "2024-01-15", "Financial Times", "Iran-Israel-USA"),
        ("Ukraine Drone Strike Hits Russian Oil Refinery",
         "Ukrainian drones damaged three major Russian oil refineries this week, temporarily reducing Russian fuel output by 12%.",
         "2024-03-20", "AP News", "Russia-Ukraine"),
        ("India's Edible Oil Import Bill Rises 40%",
         "India's palm oil and sunflower oil imports have surged 40% in cost as Ukraine war cuts sunflower supplies from the Black Sea region.",
         "2022-05-10", "Economic Times", "Russia-Ukraine"),
        ("Gold Hits Record ₹75,000 per 10g Amid Geopolitical Tensions",
         "Gold prices in India crossed ₹75,000 per 10 grams as investors flee to safe-haven assets amid escalating Middle East tensions.",
         "2024-10-25", "Mint", "Iran-Israel-USA"),
        ("US Imposes New Iran Sanctions Over Weapons Supply to Russia",
         "Washington announces sweeping new sanctions on Iranian entities supplying drones and ammunition used by Russian forces in Ukraine.",
         "2023-09-14", "Wall Street Journal", "Iran-Israel-USA"),
        ("Petrol Prices in India Unchanged Despite Crude Surge",
         "Despite crude oil touching $110/barrel, Indian government holds petrol and diesel prices stable through fuel subsidies.",
         "2022-03-25", "NDTV", "Russia-Ukraine"),
        ("Russia Threatens Oil Production Cuts in Retaliation",
         "Moscow signals potential reductions in OPEC+ compliance as leverage against Western pressure over Ukraine conflict.",
         "2023-11-30", "Al Jazeera", "Russia-Ukraine"),
        ("Middle East Crisis Pushes India Inflation to 8-Year High",
         "Fuel and food inflation driven by geopolitical disruptions has pushed India's CPI to its highest point since 2014.",
         "2024-05-15", "Business Standard", "Iran-Israel-USA"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO news (title, description, date, source, conflict) VALUES (?,?,?,?,?)",
        news_items
    )

    # ── Default Users ───────────────────────────────────────────
    # Regular user
    default_password_hash = generate_password_hash('admin123')
    cur.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, is_admin, created_at) VALUES (?,?,?,?,?)",
        ('admin', 'user@example.com', default_password_hash, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    
    # Admin user
    admin_password_hash = generate_password_hash('admin@1234')
    cur.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, is_admin, created_at) VALUES (?,?,?,?,?)",
        ('admin_user', 'admin@gmail.com', admin_password_hash, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )

    conn.commit()
    conn.close()
    print("✅  Database initialised successfully.")


def get_latest_prices_from_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.name, c.category, c.symbol, p.price, p.date
        FROM prices p JOIN commodities c ON c.id=p.commodity_id
        WHERE p.date=(SELECT MAX(p2.date) FROM prices p2 WHERE p2.commodity_id=c.id)
        ORDER BY c.id
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def build_live_snapshot(latest_rows, timestamp=None):
    timestamp = timestamp or datetime.now().isoformat()
    snapshot = []
    
    # Get real-time prices
    real_time_prices = get_real_time_commodity_prices()
    
    for row in latest_rows:
        current_price = row["price"]
        commodity_name = row["name"]
        
        # Use real-time price if available, otherwise apply small random change
        if commodity_name in real_time_prices:
            # Use real-time price with small random variation (±0.5%) to simulate market movement
            real_price = real_time_prices[commodity_name]
            variation = random.uniform(-0.5, 0.5) / 100
            live_price = round(real_price * (1 + variation), 2)
        else:
            # Fallback: small random change for commodities without real-time data
            change_percent = random.uniform(-0.5, 0.5)
            live_price = round(current_price * (1 + change_percent / 100), 2)
        
        snapshot.append({
            "id": row.get("id", row.get("commodity_id")),
            "commodity_id": row.get("id", row.get("commodity_id")),
            "name": row["name"],
            "category": row.get("category", ""),
            "symbol": row.get("symbol", ""),
            "price": live_price,
            "date": timestamp,
        })
    return snapshot


def append_live_snapshot():
    if not LIVE_PRICE_DATASETS:
        base = get_latest_prices_from_db()
    else:
        base = [
            {
                "id": row.get("id", row.get("commodity_id")),
                "commodity_id": row.get("commodity_id", row.get("id")),
                "name": row["name"],
                "category": row.get("category", ""),
                "symbol": row.get("symbol", ""),
                "price": row["price"],
            }
            for row in LIVE_PRICE_DATASETS[-1]
        ]
    snapshot = build_live_snapshot(base)
    LIVE_PRICE_DATASETS.append(snapshot)
    return snapshot


def initialize_live_price_datasets(count=10):
    for _ in range(count):
        append_live_snapshot()
        time.sleep(0.1)


def get_latest_live_snapshot():
    if LIVE_PRICE_DATASETS:
        return LIVE_PRICE_DATASETS[-1]
    return append_live_snapshot()


def get_live_trend_points(commodity, rate, limit=10):
    points = []
    for snapshot in list(LIVE_PRICE_DATASETS)[-limit:]:
        for item in snapshot:
            if item["name"] == commodity:
                points.append({
                    "date": item["date"],
                    "price_inr": to_inr(commodity, item["price"], rate),
                    "price_raw": item["price"],
                })
    return points


def update_prices_periodically():
    """Background thread to update live price datasets with real-time data and fetch news."""
    snapshot_counter = 0
    last_api_update = 0
    last_news_update = 0
    
    while True:
        try:
            current_time = time.time()
            
            # Update real-time prices every 3 minutes (180 seconds) for faster refresh in deployment
            if current_time - last_api_update >= 180:
                try:
                    fresh_prices = get_real_time_commodity_prices()
                    if fresh_prices:
                        print(f"✅ Real-time prices refreshed: {len(fresh_prices)} commodities")
                    last_api_update = current_time
                except Exception as e:
                    print(f"⚠️ Real-time API update failed: {e}")
            
            # Update news every 10 minutes (600 seconds)
            if current_time - last_news_update >= 600:
                try:
                    update_database_with_news()
                    last_news_update = current_time
                except Exception as e:
                    print(f"⚠️ News update failed: {e}")
            
            # Generate live snapshots every 2 seconds for smoother updates
            append_live_snapshot()
            snapshot_counter += 1
            
        except Exception as e:
            print(f"⚠️ Error updating data: {e}")
            # Fallback to basic snapshot generation
            try:
                append_live_snapshot()
            except Exception as e2:
                print(f"⚠️ Fallback snapshot failed: {e2}")
        
        time.sleep(2)  # Reduced sleep time for faster updates
        
        # Print status every 30 snapshots
        if snapshot_counter % 30 == 0:
            print(f"🔄 Live update at {datetime.now().strftime('%H:%M:%S')} | Snapshots: {len(LIVE_PRICE_DATASETS)}")


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════

USD_COMMODITIES = {"Crude Oil", "Gold", "Silver", "Natural Gas"}

def to_inr(name: str, price: float, rate: float) -> float:
    if name == "Gold":
        # USD/Oz → ₹/10g
        return round(price * rate / 31.1035 * 10, 2)
    if name == "Silver":
        # USD/Oz → ₹/gram
        return round(price * rate / 31.1035, 2)
    if name == "Crude Oil":
        # USD/Barrel → ₹/Barrel
        return round(price * rate, 2)
    if name == "Natural Gas":
        # USD/MMBtu → ₹/MMBtu
        return round(price * rate, 2)
    return round(price, 2)  # already INR

def inr_label(name: str) -> str:
    labels = {
        "Crude Oil":   "₹/Barrel",
        "Petrol":      "₹/Litre",
        "Diesel":      "₹/Litre",
        "Gold":        "₹/10g",
        "Silver":      "₹/gram",
        "Wheat":       "₹/Quintal",
        "Rice":        "₹/Quintal",
        "Edible Oil":  "₹/Litre",
        "Natural Gas": "₹/MMBtu",
    }
    return labels.get(name, "₹")


# ══════════════════════════════════════════════════════════════
#  AUTHENTICATION ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        login_input = request.form.get('username')  # This can be username or email
        password = request.form.get('password')
        
        if not login_input or not password:
            flash('Please provide both username/email and password', 'error')
            return render_template("login.html")
        
        conn = get_db()
        cur = conn.cursor()
        # Check if input is email or username
        if '@' in login_input:
            cur.execute("SELECT id, username, email, password_hash, is_admin, oauth_provider, oauth_id FROM users WHERE email = ?", (login_input,))
        else:
            cur.execute("SELECT id, username, email, password_hash, is_admin, oauth_provider, oauth_id FROM users WHERE username = ?", (login_input,))
        
        row = cur.fetchone()
        conn.close()
        
        if row and check_password_hash(row['password_hash'], password):
            user = User(row['id'], row['username'], row['email'], row['password_hash'], 
                       row['is_admin'], row['oauth_provider'], row['oauth_id'])
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username/email or password', 'error')
    
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not email or not password or not confirm_password:
            flash('Please fill in all fields', 'error')
            return render_template("register.html")
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template("register.html")
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template("register.html")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Check if username or email already exists
        cur.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
        existing_user = cur.fetchone()
        
        if existing_user:
            conn.close()
            flash('Username or email already exists', 'error')
            return render_template("register.html")
        
        # Create new user
        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, email, password_hash, is_admin, oauth_provider, oauth_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (username, email, password_hash, 0, None, None, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template("register.html")

# ══════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", page="dashboard")

@app.route("/commodities")
@login_required
def commodities_page():
    return render_template("commodities.html", page="commodities")

@app.route("/war-events")
@login_required
def war_events_page():
    return render_template("war_events.html", page="war_events")

@app.route("/price-trends")
@login_required
def price_trends_page():
    return render_template("price_trends.html", page="price_trends")

@app.route("/news")
@login_required
def news_page():
    return render_template("news.html", page="news")

@app.route("/predict")
@login_required
def predict_page():
    return render_template("predict.html", page="predict")


# ══════════════════════════════════════════════════════════════
#  API — DASHBOARD SUMMARY
# ══════════════════════════════════════════════════════════════

@app.route("/api/dashboard")
def api_dashboard():
    rate = get_usd_inr_rate()
    conn = get_db(); cur = conn.cursor()
    live_snapshot = get_latest_live_snapshot()
    prev_snapshot = LIVE_PRICE_DATASETS[-2] if len(LIVE_PRICE_DATASETS) > 1 else []

    def kpi(name):
        latest = next((item for item in live_snapshot if item["name"] == name), None)
        previous = next((item for item in prev_snapshot if item["name"] == name), None)
        if latest:
            cur_price = latest["price"]
            prev = previous["price"] if previous else cur_price
        else:
            cur.execute("""
                SELECT p.price FROM prices p
                JOIN commodities c ON c.id=p.commodity_id
                WHERE c.name=? ORDER BY p.date DESC LIMIT 2
            """, (name,))
            rows = cur.fetchall()
            cur_price = rows[0]["price"] if rows else 0
            prev = rows[1]["price"] if len(rows) > 1 else cur_price
        change = round(((cur_price - prev) / prev) * 100, 1) if prev else 0
        inr_price = to_inr(name, cur_price, rate)
        return {"price": inr_price, "change": change, "unit": inr_label(name), "raw": cur_price}

    oil     = kpi("Crude Oil")
    gold    = kpi("Gold")
    wheat   = kpi("Wheat")
    petrol  = kpi("Petrol")

    cur.execute("SELECT COUNT(*) AS n FROM war_events WHERE impact='high'")
    high_events = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM war_events")
    total_events = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM news")
    total_news = cur.fetchone()["n"]

    # Recent price alerts check
    alerts_triggered = []
    cur.execute("""
        SELECT a.id, c.name, a.threshold, a.direction,
               (SELECT p.price FROM prices p WHERE p.commodity_id=c.id ORDER BY p.date DESC LIMIT 1) AS latest
        FROM alerts a JOIN commodities c ON c.id=a.commodity_id
        WHERE a.active=1
    """)
    for row in cur.fetchall():
        if row["latest"] is None:
            continue
        live = next((item for item in live_snapshot if item["name"] == row["name"]), None)
        latest_price = live["price"] if live else row["latest"]
        latest_inr = to_inr(row["name"], latest_price, rate)
        if row["direction"] == "above" and latest_inr > row["threshold"]:
            alerts_triggered.append({
                "commodity": row["name"],
                "message": f"{row['name']} is ₹{latest_inr:,.0f} — above your alert of ₹{row['threshold']:,.0f}",
                "severity": "high"
            })
        elif row["direction"] == "below" and latest_inr < row["threshold"]:
            alerts_triggered.append({
                "commodity": row["name"],
                "message": f"{row['name']} is ₹{latest_inr:,.0f} — below your alert of ₹{row['threshold']:,.0f}",
                "severity": "low"
            })

    conn.close()
    return jsonify({
        "oil":    oil,
        "gold":   gold,
        "wheat":  wheat,
        "petrol": petrol,
        "high_impact_events": high_events,
        "total_events":  total_events,
        "total_news":    total_news,
        "usd_inr_rate":  round(rate, 2),
        "alerts":        alerts_triggered,
    })


# ══════════════════════════════════════════════════════════════
#  API — COMMODITIES
# ══════════════════════════════════════════════════════════════

@app.route("/api/commodities", methods=["GET"])
def api_commodities():
    category = request.args.get("category","").strip()
    conn = get_db(); cur = conn.cursor()
    if category:
        cur.execute("SELECT * FROM commodities WHERE category=? ORDER BY id", (category,))
    else:
        cur.execute("SELECT * FROM commodities ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"data": rows, "total": len(rows)})

@app.route("/api/commodities", methods=["POST"])
def api_create_commodity():
    body = request.get_json(force=True) or {}
    name     = (body.get("name")     or "").strip()
    category = (body.get("category") or "").strip()
    if not name or not category:
        return jsonify({"error": "name and category required"}), 400
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO commodities (name, category, unit, symbol) VALUES (?,?,?,?)",
                    (name, category, body.get("unit","INR"), body.get("symbol","📦")))
        conn.commit(); nid = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close(); return jsonify({"error": "Commodity already exists"}), 409
    conn.close()
    return jsonify({"id": nid, "name": name, "category": category}), 201

@app.route("/api/commodities/<int:cid>", methods=["DELETE"])
def api_delete_commodity(cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM commodities WHERE id=?", (cid,))
    if not cur.fetchone():
        conn.close(); return jsonify({"error": "Not found"}), 404
    cur.execute("DELETE FROM prices WHERE commodity_id=?", (cid,))
    cur.execute("DELETE FROM commodities WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return jsonify({"message": "Deleted"})


# ══════════════════════════════════════════════════════════════
#  API — PRICES
# ══════════════════════════════════════════════════════════════

@app.route("/api/prices/latest")
def api_prices_latest():
    rate = get_usd_inr_rate()
    live_rows = get_latest_live_snapshot()
    prev_snapshot = LIVE_PRICE_DATASETS[-2] if len(LIVE_PRICE_DATASETS) > 1 else []

    rows = []
    for r in live_rows:
        row = dict(r)
        row["price_inr"]  = to_inr(row["name"], row["price"], rate)
        row["unit_label"] = inr_label(row["name"])
        prev = next((item["price"] for item in prev_snapshot if item["name"] == row["name"]), row["price"])
        row["change"] = round(((row["price"] - prev) / prev) * 100, 1) if prev else 0
        rows.append(row)

    return jsonify({"data": rows, "usd_inr_rate": round(rate, 2), "live_datasets": len(LIVE_PRICE_DATASETS)})

@app.route("/api/prices/trends")
def api_prices_trends():
    commodity = request.args.get("commodity", "Crude Oil").strip()
    rate = get_usd_inr_rate()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT p.date, p.price, c.name
        FROM prices p JOIN commodities c ON c.id=p.commodity_id
        WHERE c.name=?
        ORDER BY p.date
    """, (commodity,))
    rows = []
    for r in cur.fetchall():
        rows.append({
            "date":      r["date"],
            "price_inr": to_inr(r["name"], r["price"], rate),
            "price_raw": r["price"],
        })
    conn.close()

    live_points = get_live_trend_points(commodity, rate, limit=10)
    rows.extend(live_points)
    rows = sorted(rows, key=lambda item: item["date"])
    # Only keep the most recent 20 entries to avoid overwhelming charts.
    if len(rows) > 20:
        rows = rows[-20:]

    return jsonify({"data": rows, "commodity": commodity, "unit": inr_label(commodity), "live_datasets": len(LIVE_PRICE_DATASETS)})

@app.route("/api/prices/all-trends")
def api_all_trends():
    """Returns all commodity trend data for the multi-chart view."""
    rate = get_usd_inr_rate()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT p.date, c.name, p.price
        FROM prices p JOIN commodities c ON c.id=p.commodity_id
        ORDER BY p.date, c.id
    """)
    pivot = {}
    for r in cur.fetchall():
        d = r["date"]
        pivot.setdefault(d, {"date": d})
        pivot[d][r["name"]] = to_inr(r["name"], r["price"], rate)
    conn.close()

    commodities = []
    cur2 = get_db().cursor()
    cur2.execute("SELECT name, symbol FROM commodities ORDER BY id")
    for r in cur2.fetchall():
        commodities.append({"name": r["name"], "symbol": r["symbol"], "unit": inr_label(r["name"])})

    return jsonify({"data": list(pivot.values()), "commodities": commodities, "usd_inr_rate": round(rate,2)})

@app.route("/api/prices/comparison")
def api_prices_comparison():
    before = request.args.get("before", "2022-01")
    after  = request.args.get("after",  "2022-03")
    rate   = get_usd_inr_rate()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT c.name,
               MAX(CASE WHEN p.date=? THEN p.price END) AS bp,
               MAX(CASE WHEN p.date=? THEN p.price END) AS ap
        FROM prices p JOIN commodities c ON c.id=p.commodity_id
        WHERE p.date IN (?,?)
        GROUP BY c.id, c.name
    """, (before, after, before, after))
    result = []
    for r in cur.fetchall():
        if r["bp"] and r["ap"]:
            b = to_inr(r["name"], r["bp"], rate)
            a = to_inr(r["name"], r["ap"], rate)
            chg = round(((a - b) / b) * 100, 1) if b else 0
            result.append({"commodity": r["name"], "before": b, "after": a, "change": chg, "unit": inr_label(r["name"])})
    conn.close()
    return jsonify({"data": result, "before": before, "after": after})

@app.route("/api/prices", methods=["POST"])
def api_add_price():
    body  = request.get_json(force=True) or {}
    cid   = body.get("commodity_id")
    price = body.get("price")
    date  = (body.get("date") or "").strip()
    if not all([cid, price is not None, date]):
        return jsonify({"error": "commodity_id, price and date required"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM commodities WHERE id=?", (cid,))
    if not cur.fetchone():
        conn.close(); return jsonify({"error": "Commodity not found"}), 404
    try:
        cur.execute("INSERT INTO prices (commodity_id, price, date) VALUES (?,?,?)", (cid, price, date))
        conn.commit(); nid = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close(); return jsonify({"error": "Price for this date already exists"}), 409
    conn.close()
    return jsonify({"id": nid}), 201


# ══════════════════════════════════════════════════════════════
#  API — WAR EVENTS
# ══════════════════════════════════════════════════════════════

@app.route("/api/war-events", methods=["GET"])
def api_war_events():
    impact   = request.args.get("impact",   "").strip()
    conflict = request.args.get("conflict", "").strip()
    conn = get_db(); cur = conn.cursor()
    query  = "SELECT * FROM war_events"
    params = []
    filters = []
    if impact:
        filters.append("impact=?"); params.append(impact)
    if conflict:
        filters.append("conflict=?"); params.append(conflict)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY date"
    cur.execute(query, params)
    rows  = [dict(r) for r in cur.fetchall()]
    total = len(rows)
    for i, row in enumerate(rows):
        row["position"] = round((i / max(total - 1, 1)) * 82 + 5, 1)
    conn.close()
    return jsonify({"data": rows, "total": total})

@app.route("/api/war-events", methods=["POST"])
def api_create_war_event():
    body   = request.get_json(force=True) or {}
    name   = (body.get("event_name")  or "").strip()
    date   = (body.get("date")        or "").strip()
    desc   = (body.get("description") or "").strip()
    conf   = (body.get("conflict")    or "Russia-Ukraine").strip()
    impact = (body.get("impact")      or "medium").strip()
    if not name or not date:
        return jsonify({"error": "event_name and date required"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO war_events (event_name, date, description, conflict, impact) VALUES (?,?,?,?,?)",
                (name, date, desc, conf, impact))
    conn.commit(); nid = cur.lastrowid; conn.close()
    return jsonify({"id": nid}), 201

@app.route("/api/war-events/<int:eid>", methods=["DELETE"])
def api_delete_war_event(eid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM war_events WHERE id=?", (eid,))
    if not cur.fetchone():
        conn.close(); return jsonify({"error": "Not found"}), 404
    cur.execute("DELETE FROM war_events WHERE id=?", (eid,))
    conn.commit(); conn.close()
    return jsonify({"message": "Deleted"})


# ══════════════════════════════════════════════════════════════
#  API — NEWS
# ══════════════════════════════════════════════════════════════

@app.route("/api/news", methods=["POST"])
def api_add_news():
    body     = request.get_json(force=True) or {}
    title    = (body.get("title")       or "").strip()
    desc     = (body.get("description") or "").strip()
    date     = (body.get("date")        or "").strip()
    source   = (body.get("source")      or "Manual").strip()
    conflict = (body.get("conflict")    or "General").strip()
    if not title or not date:
        return jsonify({"error": "title and date required"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO news (title, description, date, source, conflict) VALUES (?,?,?,?,?)",
                (title, desc, date, source, conflict))
    conn.commit(); nid = cur.lastrowid; conn.close()
    return jsonify({"id": nid}), 201

@app.route("/api/news", methods=["GET"])
def api_news():
    conflict = request.args.get("conflict", "").strip()
    search   = request.args.get("q", "").strip()
    conn = get_db(); cur = conn.cursor()
    query  = "SELECT * FROM news"
    params = []
    filters = []
    if conflict:
        filters.append("conflict=?"); params.append(conflict)
    if search:
        filters.append("(title LIKE ? OR description LIKE ?)"); params += [f"%{search}%", f"%{search}%"]
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY date DESC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"data": rows, "total": len(rows)})

@app.route("/api/news/<int:news_id>", methods=["GET"])
@login_required
def api_get_single_news(news_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "News not found"}), 404

@app.route("/api/news/<int:news_id>", methods=["PUT"])
@login_required
def api_update_news(news_id):
    if not current_user.is_admin:
        return jsonify({"error": "Admin access required"}), 403
        
    body = request.get_json(force=True) or {}
    title = (body.get("title") or "").strip()
    desc = (body.get("description") or "").strip()
    date = (body.get("date") or "").strip()
    source = (body.get("source") or "").strip()
    conflict = (body.get("conflict") or "General").strip()
    
    if not title or not date:
        return jsonify({"error": "title and date required"}), 400
    
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        UPDATE news SET title=?, description=?, date=?, source=?, conflict=? 
        WHERE id=?
    """, (title, desc, date, source, conflict, news_id))
    
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "News not found"}), 404
        
    conn.commit(); conn.close()
    return jsonify({"message": "News updated successfully"})

@app.route("/api/news/<int:news_id>", methods=["DELETE"])
@login_required
def api_delete_news(news_id):
    if not current_user.is_admin:
        return jsonify({"error": "Admin access required"}), 403
        
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM news WHERE id=?", (news_id,))
    
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "News not found"}), 404
        
    conn.commit(); conn.close()
    return jsonify({"message": "News deleted successfully"})


# ══════════════════════════════════════════════════════════════
#  API — ALERTS
# ══════════════════════════════════════════════════════════════

@app.route("/api/alerts", methods=["GET"])
def api_get_alerts():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT a.*, c.name AS commodity_name, c.symbol
        FROM alerts a JOIN commodities c ON c.id=a.commodity_id
        ORDER BY a.id DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"data": rows})

@app.route("/api/alerts", methods=["POST"])
def api_create_alert():
    body      = request.get_json(force=True) or {}
    cid       = body.get("commodity_id")
    threshold = body.get("threshold")
    direction = (body.get("direction") or "above").strip()
    if not cid or threshold is None:
        return jsonify({"error": "commodity_id and threshold required"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO alerts (commodity_id, threshold, direction, active, created_at) VALUES (?,?,?,1,?)",
                (cid, threshold, direction, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); nid = cur.lastrowid; conn.close()
    return jsonify({"id": nid}), 201

@app.route("/api/alerts/<int:aid>", methods=["DELETE"])
def api_delete_alert(aid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM alerts WHERE id=?", (aid,))
    conn.commit(); conn.close()
    return jsonify({"message": "Deleted"})


# ══════════════════════════════════════════════════════════════
#  API — ML PREDICTION
# ══════════════════════════════════════════════════════════════

@app.route("/api/predict")
def api_predict():
    commodity = request.args.get("commodity", "Crude Oil").strip()
    steps     = int(request.args.get("steps", 4))
    rate      = get_usd_inr_rate()

    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT p.date, p.price
        FROM prices p JOIN commodities c ON c.id=p.commodity_id
        WHERE c.name=? ORDER BY p.date
    """, (commodity,))
    rows = cur.fetchall()
    conn.close()

    if len(rows) < 4:
        return jsonify({"error": "Not enough data for prediction"}), 400

    prices_list = [r["price"] for r in rows]
    dates_list  = [r["date"]  for r in rows]

    def parse_year_month(date_str):
        if "T" in date_str:
            date_str = date_str.split("T", 1)[0]
        parts = date_str.split("-")
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
        raise ValueError(f"Unsupported date format for prediction: {date_str}")

    # Simple Linear Regression (no external ML library needed)
    n = len(prices_list)
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(prices_list) / n
    num   = sum((x[i] - x_mean) * (prices_list[i] - y_mean) for i in range(n))
    denom = sum((x[i] - x_mean) ** 2 for i in range(n)) or 1
    slope = num / denom
    intercept = y_mean - slope * x_mean

    # Generate future predictions
    predictions = []
    last_date = dates_list[-1]
    year, month = parse_year_month(last_date)
    for s in range(1, steps + 1):
        month += 3
        if month > 12:
            month -= 12; year += 1
        future_date  = f"{year}-{month:02d}"
        future_price = intercept + slope * (n - 1 + s)
        future_price = max(future_price, prices_list[-1] * 0.7)  # sanity floor
        predictions.append({
            "date":         future_date,
            "predicted":    round(future_price, 2),
            "predicted_inr": to_inr(commodity, future_price, rate),
        })

    # Historical with INR
    historical = [{
        "date": r["date"],
        "price": r["price"],
        "price_inr": to_inr(commodity, r["price"], rate),
    } for r in rows]

    # Insights
    last_inr = to_inr(commodity, prices_list[-1], rate)
    pred_inr  = predictions[-1]["predicted_inr"]
    trend     = "📈 Rising" if pred_inr > last_inr else "📉 Falling"
    pct       = round(((pred_inr - last_inr) / last_inr) * 100, 1) if last_inr else 0

    return jsonify({
        "commodity":   commodity,
        "unit":        inr_label(commodity),
        "historical":  historical,
        "predictions": predictions,
        "slope":       round(slope, 4),
        "intercept":   round(intercept, 4),
        "insight":     f"{trend}: Predicted {abs(pct):.1f}% {'increase' if pct > 0 else 'decrease'} over next {steps * 3} months",
        "ml_available": True,
    })

@app.route("/api/exchange-rate")
def api_exchange_rate():
    rate = get_usd_inr_rate()
    age  = int(time.time() - _rate_cache["fetched_at"])
    return jsonify({"usd_inr": round(rate, 4), "cached_ago": age, "ttl": _RATE_TTL})


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    initialize_live_price_datasets(10)
    # Start background thread to update prices with real-time data
    updater_thread = threading.Thread(target=update_prices_periodically, daemon=True)
    updater_thread.start()
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("DEBUG", "False").lower() == "true"
    print(f"🚀  War Impact Commodity Analyzer → http://0.0.0.0:{port}")
    print(f"📊  Pages: Dashboard | Commodities | Price Trends | War Events | News | Predict")
    print(f"🔄  Background thread: Updating prices every 2s, APIs every 3m, News every 10m")
    app.run(debug=debug_mode, host="0.0.0.0", port=port, threaded=True)
