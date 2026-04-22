# Deployment & Troubleshooting Guide

## Issues Fixed

### 1. **Syntax Errors** ✅
- **Duplicate Code Block (Line 453-467)**: Removed unreachable duplicate news processing code
- **Duplicate Entry Point**: Removed duplicate `if __name__ == "__main__"` block that was overwriting the main entry point

### 2. **Real-Time Price Data Stuck** ✅

#### Root Causes:
- API keys not configured → prices fall back to cached/simulated data
- Long cache TTL (5 minutes) → updates felt slow
- Background thread logic flawed → wasn't fetching real-time data effectively
- Production deployments often blocked external API calls

#### Fixes Applied:
1. **Reduced Cache TTL**: 5 minutes → 3 minutes for faster updates
2. **Improved Background Thread**: 
   - Snapshots every 2 seconds (was 1s, now better balanced)
   - Real-time API fetch every 3 minutes (was 5 minutes)
   - News updates every 10 minutes (was 15 minutes)
   - Better error handling and logging

3. **Better Fallback Mechanism**: If real-time APIs fail, small random variations simulate market movement

---

## Deployment Checklist

### Local Development
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API keys
cp war_analyzer/.env.example war_analyzer/.env
# Edit .env and add your API keys:
# - ALPHA_VANTAGE_API_KEY (from https://www.alphavantage.co/support/#api-key)
# - NEWS_API_KEY (from https://newsapi.org/)

# 3. Run the app
cd war_analyzer
python app.py
```

### Production Deployment

#### Using Gunicorn (Recommended)
```bash
# Install Gunicorn
pip install gunicorn

# Run with multiple workers
gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 60 app:app
```

#### Using Docker
Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY war_analyzer/ .
ENV FLASK_APP=app.py
ENV DEBUG=False
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "--timeout", "60", "app:app"]
```

Build and run:
```bash
docker build -t war-analyzer .
docker run -d -p 5000:5000 --env-file war_analyzer/.env war-analyzer
```

#### Environment Variables (Production)
```bash
export ALPHA_VANTAGE_API_KEY=your-key
export NEWS_API_KEY=your-key
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export DEBUG=False
export PORT=5000
```

---

## API Keys Setup

### Alpha Vantage (for Commodity Prices)
1. Go to https://www.alphavantage.co/support/#api-key
2. Enter your email and get a **FREE API key**
3. Add to `.env`: `ALPHA_VANTAGE_API_KEY=your-key`
4. Features: Crude Oil, Gold, Silver, Natural Gas prices

### NewsAPI (for War News)
1. Go to https://newsapi.org/
2. Sign up for **FREE tier**
3. Copy your API key
4. Add to `.env`: `NEWS_API_KEY=your-key`
5. Provides real-time news from 50+ sources

---

## Troubleshooting

### Prices Still Stuck After Deployment?

**Check:**
1. **API Keys Configured**
   ```bash
   # Check if .env file is loaded
   echo $ALPHA_VANTAGE_API_KEY
   ```

2. **Network Access to External APIs**
   ```bash
   # Test connectivity
   curl -I https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=CL&apikey=YOUR_KEY
   curl -I https://query1.finance.yahoo.com/v8/finance/chart/CL=F
   ```

3. **Database Has Initial Data**
   ```bash
   # Check database exists
   ls -la war_analyzer/database.db
   ```

4. **Background Thread Running**
   - Check logs for "🔄 Live update at" messages
   - Should see "✅ Real-time prices refreshed" every 3 minutes

5. **Cache Freshness**
   - Check API: `GET /api/exchange-rate` returns `cached_ago` ≤ 20 minutes

### Prices Update Too Slowly?

**Solution:** The background thread is working correctly. Updates happen every 3 minutes from APIs and every 2 seconds for live snapshots.
- This is by design to avoid API rate limits
- Front-end charts show smooth transitions with interpolated snapshots

### High Memory Usage?

**Cause:** `LIVE_PRICE_DATASETS` deque stores 200 snapshots × 9 commodities

**Solution:**
```python
# In app.py, adjust maxlen
LIVE_PRICE_DATASETS = deque(maxlen=100)  # Reduce from 200
```

### Rate Limit Errors from APIs?

**Free Tier Limits:**
- Alpha Vantage: 5 calls/minute (standard tier)
- NewsAPI: 100 calls/day (free tier)

**Solutions:**
1. Use the improved cache (3-minute TTL)
2. Upgrade to paid API tiers for production
3. Implement Redis caching for multi-server deployments

---

## Performance Optimization

### For High-Traffic Deployments
1. Use Redis for caching
2. Implement database connection pooling
3. Use CDN for static files
4. Enable gzip compression in reverse proxy (Nginx)

### Reverse Proxy Configuration (Nginx)
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
    }

    location /static {
        alias /path/to/app/static;
        expires 1h;
        add_header Cache-Control "public, immutable";
    }
}
```

---

## Database Maintenance

### Backup Database
```bash
cp war_analyzer/database.db war_analyzer/database.db.backup.$(date +%Y%m%d)
```

### Clear Old News (Keep Last 30 Days)
```python
from datetime import datetime, timedelta
import sqlite3

conn = sqlite3.connect('database.db')
cur = conn.cursor()
thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
cur.execute("DELETE FROM news WHERE date < ?", (thirty_days_ago,))
conn.commit()
conn.close()
print("Old news cleared")
```

---

## Monitoring & Logging

### Check Application Health
```bash
# Test dashboard API
curl http://localhost:5000/api/dashboard

# Test price updates
curl http://localhost:5000/api/prices/latest

# Test exchange rate
curl http://localhost:5000/api/exchange-rate
```

### Enable Access Logs
```python
# In production, use Gunicorn with access logs
gunicorn --access-logfile - --error-logfile - app:app
```

---

## Support & Documentation

- **Alpha Vantage Docs**: https://www.alphavantage.co/documentation/
- **NewsAPI Docs**: https://newsapi.org/docs
- **Flask Deployment**: https://flask.palletsprojects.com/en/latest/deploying/
- **Gunicorn Docs**: https://docs.gunicorn.org/
