from flask import Flask
from threading import Thread
import requests
import time
import os
import pandas as pd
import ta
import datetime
import json

STATE_FILE = "state.json"

# ---------------------------
# Config
# ---------------------------
TOKEN ="8689386667:AAFhazRA-tWJK4_h5q7mlTNp5Z0J_gviGYk"   # Replace with your Telegram bot token
CHAT_ID = "8006267074"       # Replace with your chat ID
SYMBOL = "bitcoin"              # CoinGecko ID for BTC
VS_CURRENCY = "usd"
RANGE = 330

alerts_list = []
last_price = 0.0
last_time = ""

# ---------------------------
# Load & Save state
# ---------------------------
def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "last_price": last_price,
                "last_time": last_time,
                "alerts_list": alerts_list
            }, f)
    except Exception as e:
        print("State save error:", e)

def load_state():
    global last_price, last_time, alerts_list
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            last_price = data.get("last_price", 0.0)
            last_time = data.get("last_time", "")
            alerts_list = data.get("alerts_list", [])
    except:
        print("No previous state found.")

load_state()

# ---------------------------
# Telegram
# ---------------------------
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ---------------------------
# CoinGecko Data Fetch
# ---------------------------
def get_klines():
    """
    Fetch 1-day BTC prices from CoinGecko and convert to 15-min OHLC
    """
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{SYMBOL}/market_chart"
        params = {"vs_currency": VS_CURRENCY, "days": "1"}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print("CoinGecko API error:", response.text)
            return None

        data = response.json()
        if "prices" not in data:
            print("Invalid response:", data)
            return None

        prices = data["prices"]  # [timestamp, price]
        df = pd.DataFrame(prices, columns=["time", "price"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        # Fixed frequency string here
        df = df.set_index("time").resample("15min").ohlc()
        df.columns = df.columns.droplevel(0)
        df = df.reset_index()
        df["volume"] = 0  # placeholder
        return df
    except Exception as e:
        print("CoinGecko error:", e)
        return None
# ---------------------------
# Alert Logic
# ---------------------------
def check_alerts():
    global last_price

    df = get_klines()
    if df is None or len(df) < 5:
        return "NONE", last_price

    priceNow = df["close"].iloc[-1]
    price60minAgo = df["close"].iloc[-5]

    slopePer15Min = (priceNow - price60minAgo) / 4

    atr = ta.volatility.AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    ).average_true_range().iloc[-1]

    volFactor = atr * 0.5

    ema20 = ta.trend.EMAIndicator(df["close"], 20).ema_indicator()
    direction = 1 if ema20.iloc[-1] > ema20.iloc[-5] else -1

    p1 = priceNow + slopePer15Min + direction * volFactor

    if p1 >= priceNow + RANGE:
        return "BET-UP", priceNow
    elif p1 <= priceNow - RANGE:
        return "BET-DOWN", priceNow

    return "NONE", priceNow

# ---------------------------
# Flask Dashboard
# ---------------------------
app = Flask(__name__)

@app.route("/")
def home():
    alerts_html = "<br>".join(alerts_list[-10:][::-1])
    return f"""
    <h2>Crypto Bot Dashboard</h2>
    <p><b>Symbol:</b> {SYMBOL.upper()}</p>
    <p><b>Current Price:</b> {last_price}</p>
    <p><b>Last Updated:</b> {last_time}</p>
    <h3>Last Alerts:</h3>
    <p>{alerts_html}</p>
    """

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ---------------------------
# Bot Loop
# ---------------------------
def run_bot():
    global alerts_list, last_price, last_time

    last_status = None
    print("Bot started...")

    while True:
        try:
            status, price = check_alerts()
            last_price = price
            last_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if status != last_status:
                if status == "BET-UP":
                    msg = f"📈 UP | {SYMBOL.upper()} | {price}"
                elif status == "BET-DOWN":
                    msg = f"📉 DOWN | {SYMBOL.upper()} | {price}"
                else:
                    msg = f"⏸ NO SIGNAL | {SYMBOL.upper()} | {price}"

                print(msg)
                send_telegram(msg)

                alerts_list.append(msg)
                if len(alerts_list) > 50:
                    alerts_list = alerts_list[-50:]

                save_state()
                last_status = status

            time.sleep(30)
        except Exception as e:
            print("Bot error:", e)
            time.sleep(60)

# ---------------------------
# Start
# ---------------------------
if __name__ == "__main__":
    Thread(target=run_flask).start()
    Thread(target=run_bot).start()
    while True:
        time.sleep(60)
