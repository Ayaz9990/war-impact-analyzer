# 🌍 War Impact Commodity Analyzer (India)

A full-stack web application that analyzes how global conflicts — **Russia-Ukraine War** and **Iran–USA–Israel tensions** — affect commodity prices in India (₹ INR).

---

## 🎯 Features

| Feature | Description |
|---|---|
| � **Authentication** | User registration and login system |
| �📊 **Dashboard** | Live KPI cards for Crude Oil, Gold, Wheat, Petrol in ₹ INR |
| 📈 **Price Trends** | Interactive Chart.js line/bar charts with export to CSV |
| ⚔️ **War Events** | Timeline of geopolitical events with impact levels |
| 📰 **War News** | Filterable news feed: Russia-Ukraine & Iran-Israel-USA |
| 🤖 **ML Prediction** | Linear Regression forecast (no external ML libraries needed) |
| 🔔 **Price Alerts** | Set price thresholds and get alerted on dashboard |
| 💱 **Live Exchange Rate** | Real-time USD→INR conversion (cached 20 minutes) |
| 📊 **Real-time Prices** | Live commodity prices from Alpha Vantage API |
| ⚡ **Stock Market Live Updates** | 2.5-second price updates with animations & sparklines |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.x + Flask |
| **Frontend** | HTML5, CSS3, JavaScript (ES6) |
| **UI Framework** | Bootstrap 5 |
| **Charts** | Chart.js 4 |
| **Database** | SQLite (database.db) |
| **ML** | Pure Python (stdlib) Linear Regression |

---

## 📂 Project Structure

```
war-analyzer/
├── app.py                  ← Main Flask application
├── requirements.txt        ← Python dependencies
├── database.db             ← SQLite database (auto-created)
├── README.md               ← This file
│
├── models/
│   ├── __init__.py
│   └── predictor.py        ← Linear Regression model
│
├── utils/
│   ├── __init__.py
│   └── helpers.py          ← Utility functions
│
├── templates/
│   ├── base.html           ← Master layout (sidebar, header)
│   ├── dashboard.html      ← Main dashboard with KPIs + charts
│   ├── commodities.html    ← Commodity list with comparison chart
│   ├── price_trends.html   ← Interactive price trend charts
│   ├── war_events.html     ← War events timeline
│   ├── news.html           ← War news feed
│   └── predict.html        ← ML price prediction
│
└── static/
    └── css/
        └── main.css        ← Custom dark theme
```

---

## � Authentication

The application includes a complete user authentication system with registration and login.

### Default Users

| User Type | Username/Email | Password | Role |
|---|---|---|---|
| Regular User | `admin` | `admin123` | User |
| Admin User | `admin_user` / `admin@gmail.com` | `admin@1234` | Admin |

### User Registration

- **Register**: New users can create accounts via `/register`
- **Login**: Existing users can login with username/email and password
- **Admin Access**: Use admin credentials for elevated permissions

---

## 📊 Real-Time Commodity Prices

The application fetches live commodity prices from financial APIs to provide accurate, real-time data.

### API Configuration

1. **Get Alpha Vantage API Key** (Free):
   - Visit [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
   - Sign up for a free API key
   - Copy `.env.example` to `.env` and add your key:
     ```
     ALPHA_VANTAGE_API_KEY=your-api-key-here
     SECRET_KEY=your-secret-key
     ```

2. **Supported Commodities**:
   - 🛢️ **Crude Oil** (WTI) - Primary: Alpha Vantage, Fallback: Yahoo Finance
   - 🥇 **Gold** - Primary: Alpha Vantage, Fallback: Yahoo Finance  
   - 🥈 **Silver** - Primary: Alpha Vantage, Fallback: Yahoo Finance
   - 🔥 **Natural Gas** - Primary: Alpha Vantage, Fallback: Yahoo Finance

3. **Fallback System**:
   - If Alpha Vantage fails, automatically falls back to Yahoo Finance
   - If all APIs fail, uses small random variations (±0.5%) around last known prices
   - Prices update every 5 minutes from APIs, live snapshots every second

### Without API Key

The application works without an API key but will show simulated price movements instead of real data.

---

## 📰 Automatic War News Updates

The application automatically fetches and displays real-time war and conflict news from multiple reliable sources.

### News Sources

- **📰 NewsAPI** (Primary): Comprehensive news articles with full content
- **📡 RSS Feeds**: BBC News, Reuters, Al Jazeera, CNN, The Guardian
- **🌐 Google News**: Additional coverage for breaking news
- **🔄 Auto-Updates**: News refreshes every 15 minutes automatically

### News Features

- **🔒 Admin Controls**: Only admins can add, edit, or delete news articles
- **👁️ Read-Only Access**: Regular users can only view news
- **⚡ Real-Time UI Updates**: Interface updates every 2 minutes without page refresh
- **🔍 Smart Filtering**: Only war/conflict related news (no spam)
- **🏷️ Conflict Classification**: Automatic categorization (Russia-Ukraine, Iran-Israel-USA, China-Taiwan, India-Pakistan, General)
- **🔄 Manual Refresh**: Click "Refresh News" button for instant updates
- **📊 Status Indicator**: Shows when news was last updated
- **🔎 Search & Filter**: Filter by conflict type and search headlines

### Admin Features

- **➕ Add News**: Create new news articles manually
- **✏️ Edit News**: Click edit button on any news card to modify
- **🗑️ Delete News**: Remove articles with confirmation
- **🎯 Conflict Categories**: Assign articles to specific conflict types

### API Configuration

1. **Get NewsAPI Key** (Free tier available):
   - Visit [NewsAPI](https://newsapi.org/)
   - Sign up for a free API key (500 requests/day)
   - Add to your `.env` file:
     ```
     NEWS_API_KEY=your-news-api-key-here
     ```

2. **Fallback System**:
   - If NewsAPI fails, automatically uses RSS feeds
   - If RSS feeds fail, uses Google News as final fallback
   - Always ensures news availability even without API keys

### Without API Key

The application works without a NewsAPI key but will rely on RSS feeds and Google News for news updates.

---

## ⚡ Stock Market-Style Live Updates

The dashboard now features real-time price updates just like professional stock market applications:

### Live Update Features

- **⚡ Ultra-Fast Updates**: Prices refresh every 2.5 seconds for real-time feel
- **📊 Live Indicator**: Animated "LIVE" badge with current timestamp
- **📈 Trend Icons**: 📈📉 indicators show price direction (up/down)
- **💫 Price Animations**: 
  - Flashing prices when they change
  - Color-coded card highlights (green for up, red for down)
  - Smooth transitions and pulse effects
- **📉 Mini Sparklines**: Tiny trend charts on each KPI card showing recent price movement
- **📊 Enhanced Change Display**: Shows both percentage and absolute price changes

### Animation Effects

- **Price Flash**: Prices glow blue when updated
- **Card Pulse**: Cards scale and glow when prices change significantly  
- **Trend Colors**: Green glow for price increases, red glow for decreases
- **Sparkline Colors**: Green/red lines matching price trends
- **Live Dot**: Pulsing green dot indicating live data feed

### Performance Optimized

- **Smart Caching**: API calls every 5 minutes, UI updates every 2.5 seconds
- **Fallback System**: Continues working even if APIs are unavailable
- **Efficient Rendering**: Canvas-based sparklines for smooth performance

---

## 🚀 How to Run

### Step 1 — Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2 — Setup Environment (Optional for Real-Time Data)

```bash
cp .env.example .env
# Edit .env with your Alpha Vantage API key (optional but recommended)
```

### Step 3 — Run the App

```bash
python app.py
```

### Step 4 — Open in Browser

```
http://localhost:5000
```

The database is **auto-created** with sample data on first run. No setup needed!

---

## 📊 Commodities Tracked

| Commodity | Unit | Category |
|---|---|---|
| 🛢️ Crude Oil | ₹/Barrel | Energy |
| ⛽ Petrol | ₹/Litre | Energy |
| 🚛 Diesel | ₹/Litre | Energy |
| 🥇 Gold | ₹/10g | Precious Metals |
| 🥈 Silver | ₹/gram | Precious Metals |
| 🌾 Wheat | ₹/Quintal | Agriculture |
| 🍚 Rice | ₹/Quintal | Agriculture |
| 🫙 Edible Oil | ₹/Litre | Agriculture |
| 🔥 Natural Gas | ₹/MMBtu | Energy |

---

## 🗄️ Database Schema

```sql
commodities  — id, name, category, unit, symbol
prices       — id, commodity_id, price, date
war_events   — id, event_name, date, description, conflict, impact
news         — id, title, description, date, source, conflict
alerts       — id, commodity_id, threshold, direction, active, created_at
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/dashboard` | KPIs + stats for dashboard |
| GET | `/api/commodities` | List all commodities |
| POST | `/api/commodities` | Add a commodity |
| DELETE | `/api/commodities/<id>` | Delete a commodity |
| GET | `/api/prices/latest` | Latest prices for all commodities |
| GET | `/api/prices/trends?commodity=Gold` | Price trend for one commodity |
| GET | `/api/prices/all-trends` | All commodity trends (normalized) |
| GET | `/api/prices/comparison` | Before/after war comparison |
| POST | `/api/prices` | Add a price record |
| GET | `/api/war-events` | List war events |
| POST | `/api/war-events` | Add a war event |
| DELETE | `/api/war-events/<id>` | Delete a war event |
| GET | `/api/news` | List news articles |
| POST | `/api/news` | Add a news article |
| GET | `/api/alerts` | List price alerts |
| POST | `/api/alerts` | Create a price alert |
| DELETE | `/api/alerts/<id>` | Delete an alert |
| GET | `/api/predict?commodity=Gold&steps=4` | ML price prediction |
| GET | `/api/exchange-rate` | Current USD→INR rate |

---

## 🤖 ML Prediction

The prediction model uses **Ordinary Least Squares (OLS) Linear Regression** implemented in pure Python (no NumPy or sklearn needed).

**Formula:**
```
y = slope × x + intercept
```
Where:
- `x` = time index (0, 1, 2, …)
- `y` = commodity price in INR
- Future prices = extend the fitted line forward

---

## 📸 Pages

1. **Dashboard** — KPI cards, trend chart selector, war impact donut chart, insights, news preview
2. **Commodities** — Sortable table with INR prices, before/after war bar chart
3. **Price Trends** — Full trend chart with CSV export, normalized multi-commodity view
4. **War Events** — Interactive timeline (alternating left/right), event table with filters
5. **War News** — Card grid with conflict filter and search
6. **ML Prediction** — Chart showing historical + forecast with signal table

---

## 👨‍💻 Made For

College Project — B.Tech / BCA / MCA  
Subject: Full-Stack Web Development / Data Analytics  
Tech: Python Flask + SQLite + Bootstrap + Chart.js

---

> ⚠️ All prices are for **educational/analytical purposes** only. Prediction outputs are not financial advice.
