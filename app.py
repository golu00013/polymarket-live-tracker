import os, time, json, requests, threading
from datetime import datetime, timedelta
from flask import Flask, render_template_string
from supabase import create_client, Client
import logging

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

TELEGRAM_TOKEN = "8399826357:AAFw3sGXnFAwfkAoFsJ1pJVdiabJNC93wy4"
TELEGRAM_CHAT_ID = "6211724721"
GAMMA = "https://gamma-api.polymarket.com"

app = Flask(__name__)
results_cache = []

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except:
        pass

def get_markets():
    try:
        r = requests.get(f"{GAMMA}/markets",
            params={"limit": 50, "active": "true", "closed": "false", "order": "volume24hr", "ascending": "false"},
            timeout=10)
        data = r.json()
        return data if isinstance(data, list) else data.get("markets", [])
    except Exception as e:
        print(f"Market error: {e}")
        return []

def is_crypto(name):
    cryptos = ["bitcoin", "ethereum", "solana", "bnb", "dogecoin", "cardano", "xrp", "ada", "litecoin", "btc", "eth", "sol", "doge"]
    return any(c in name.lower() for c in cryptos)

def get_coin_symbol(name):
    symbols = {
        "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
        "binance": "BNB", "dogecoin": "DOGE", "cardano": "ADA",
        "ripple": "XRP", "litecoin": "LTC", "polkadot": "DOT"
    }
    name_lower = name.lower()
    for key, sym in symbols.items():
        if key in name_lower:
            return sym
    return name[:5].upper()

def monitor():
    global results_cache
    history = {}
    alerted = set()
    
    TIMEFRAMES = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
    
    while True:
        try:
            markets = get_markets()
            new_results = []
            
            for m in markets:
                mid = m.get("id") or m.get("conditionId", "")
                name = m.get("question", "?")[:60]
                vol = float(m.get("volume", 0))
                
                if not is_crypto(name) or vol < 30000:
                    continue
                
                try:
                    prices = json.loads(m.get("outcomePrices", "[0.5,0.5]"))
                    yes_price = round(float(prices[0]) * 100, 1)
                except:
                    continue
                
                direction = "UP" if yes_price > 52 else ("DOWN" if yes_price < 48 else "NEUTRAL")
                if direction == "NEUTRAL":
                    continue
                
                coin = get_coin_symbol(name)
                
                if mid not in history:
                    history[mid] = {tf: [] for tf in TIMEFRAMES}
                
                for tf, interval in TIMEFRAMES.items():
                    history[mid][tf].append(direction)
                    if len(history[mid][tf]) > 3:
                        history[mid][tf].pop(0)
                    
                    h = history[mid][tf]
                    
                    # Save to Supabase
                    if supabase:
                        try:
                            supabase.table("polymarket_results").insert({
                                "coin": coin,
                                "timeframe": tf,
                                "direction": direction,
                                "price": float(yes_price),
                                "change": 0.0
                            }).execute()
                        except:
                            pass
                    
                    new_results.insert(0, {
                        "coin": coin,
                        "tf": tf,
                        "direction": direction,
                        "price": f"{yes_price}¢",
                        "vol": f"${vol:,.0f}",
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "status": "✅ 3x" if (len(h) == 3 and len(set(h)) == 1) else f"{len(h)}/3"
                    })
                    
                    if len(h) == 3 and len(set(h)) == 1:
                        key = f"{mid}_{tf}_{direction}"
                        if key not in alerted:
                            alerted.add(key)
                            e = "🟢" if direction == "UP" else "🔴"
                            send(f"{e}{e}{e} <b>3x {direction} {tf}!</b>\n\n📊 {coin}\n💰 {yes_price}¢")
            
            results_cache = new_results[:20]
            time.sleep(300)  # 5 min
            
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(30)

@app.route("/")
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Polymarket Live Tracker</title>
        <meta http-equiv="refresh" content="60">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { background: #0d0d0d; color: #fff; font-family: Arial; padding: 20px; }
            h1 { color: #00ff88; margin-bottom: 10px; }
            .info { color: #888; font-size: 12px; margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th { background: #1a1a2e; padding: 12px; text-align: left; font-weight: bold; border: 1px solid #333; }
            td { padding: 12px; border-bottom: 1px solid #222; }
            tr:hover { background: #1a1a2e; }
            .coin { font-weight: bold; font-size: 14px; }
            .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }
            .dot-up { background: #00ff88; }
            .dot-down { background: #ff4444; }
            .up { color: #00ff88; font-weight: bold; }
            .down { color: #ff4444; font-weight: bold; }
            .status { color: #ffaa00; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🤖 Polymarket Live Tracker</h1>
        <div class="info">⏰ 5 min updates | 📊 5m, 15m, 1h, 4h | 💰 Real Polymarket Data | 🔔 Telegram Alerts</div>
        <table>
            <tr>
                <th>Coin</th>
                <th>TimeFrame</th>
                <th>Direction</th>
                <th>Price</th>
                <th>Volume</th>
                <th>Status</th>
                <th>Time</th>
            </tr>
            {% for r in results %}
            <tr>
                <td class="coin">{{ r.coin }}</td>
                <td><strong>{{ r.tf }}</strong></td>
                <td>
                    <span class="dot dot-{{ 'up' if r.direction == 'UP' else 'down' }}"></span>
                    <span class="{{ 'up' if r.direction == 'UP' else 'down' }}">{{ r.direction }}</span>
                </td>
                <td>{{ r.price }}</td>
                <td>{{ r.vol }}</td>
                <td class="status">{{ r.status }}</td>
                <td>{{ r.time }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(html, results=results_cache)

if __name__ == "__main__":
    t = threading.Thread(target=monitor, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
