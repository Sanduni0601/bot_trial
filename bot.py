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
TOKEN = "8689386667:AAFhazRA-tWJK4_h5q7mlTNp5Z0J_gviGYk"
CHAT_ID = "8006267074"
SYMBOL = "BTC-USDT"
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
# KuCoin Data Fetch (FIXED)
# ---------------------------
def get_klines():
    try:
        url = f"https://api.kucoin.com/api/v1/market/candles?type=15min&symbol={SYMBOL}"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print("KuCoin error:", response.text)
            return None

        data = response.json()

        if "data" not in data:
            print("Invalid response:", data)
            return None

        candles = data["data"]

        df = pd.DataFrame(candles, columns=[
            "time", "open", "close", "high", "low", "volume", "turnover"
        ])

        # Convert types
        df["open"] = df["open"].astype(float)
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        # Reverse order (important)
        df = df.iloc[::-1].reset_index(drop=True)

        return df

    except Exception as e:
        print("Fetch error:", e)
        return None

# ---------------------------
# Alert Logic
# ---------------------------
def check_alerts():
    global last_price

    df = get_klines()

    if df is None or len(df) < 20:
        return "NONE", last_price

    # Latest actual close price
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

    # Predicted price (reduce 40 from normal prediction)
    p1 = priceNow + slopePer15Min + direction * volFactor - 60

    # Alert logic
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
    <p><b>Symbol:</b> {SYMBOL}</p>
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
                    msg = f"📈 UP | {SYMBOL} | {price}"
                elif status == "BET-DOWN":
                    msg = f"📉 DOWN | {SYMBOL} | {price}"
                else:
                    msg = f"⏸ NO SIGNAL | {SYMBOL} | {price}"

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
