# ---------------------------
# Binance Bot with Telegram & Web Dashboard
# 15m candles | 60m history | 75m future prediction
# ---------------------------

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
SYMBOL = "BTCUSDT"
RANGE = 330

# ---------------------------
# Global variables
# ---------------------------
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
# Telegram helper
# ---------------------------
def send_telegram(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    for i in range(3):  # retry 3 times
        try:
            requests.post(
                url,
                data={"chat_id": CHAT_ID, "text": message},
                timeout=20
            )
            return
        except Exception as e:
            print("Telegram Error:", e)
            time.sleep(5)


# ---------------------------
# Binance helper
# ---------------------------
def get_binance_klines():

    try:

        url = f"https://api.binance.us/api/v3/klines?symbol={SYMBOL}&interval=15m&limit=200"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print("Binance API error:", response.text)
            return None

        data = response.json()

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","tb_base","tb_quote","ignore"
        ])

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        return df

    except Exception as e:
        print("Error fetching Binance data:", e)
        return None


# ---------------------------
# Alert Logic
# ---------------------------
def check_alerts():

    global last_price

    df = get_binance_klines()

    if df is None or len(df) < 20:
        return "NONE", last_price

    priceNow = df["close"].iloc[-1]

    # ---- 60 minute history (4 candles) ----
    price60minAgo = df["close"].iloc[-5]

    slopePer15Min = (priceNow - price60minAgo) / 4

    # ---- Volatility ATR ----
    atr = ta.volatility.AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    ).average_true_range().iloc[-1]

    volFactor = atr * 0.5

    # ---- EMA trend ----
    ema20 = ta.trend.EMAIndicator(df["close"], 20).ema_indicator()

    direction = 1 if ema20.iloc[-1] > ema20.iloc[-5] else -1

    # ---- 75 minute prediction ----
    p1 = priceNow + slopePer15Min * 1 + direction * volFactor

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
    <h2>Binance Bot Dashboard</h2>
    <p><b>Symbol:</b> {SYMBOL}</p>
    <p><b>Current Price:</b> {last_price}</p>
    <p><b>Last Updated:</b> {last_time}</p>
    <h3>Last Alerts:</h3>
    <p>{alerts_html}</p>
    """


def run_flask():

    port = int(os.environ.get("PORT", 3000))

    app.run(host="0.0.0.0", port=port)


# ---------------------------
# Bot Loop
# ---------------------------
def run_bot():

    global alerts_list, last_price, last_time

    last_status = None

    print("Bot started...")

    status, price = check_alerts()

    last_price = price
    last_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    first_msg = f"Bot started | {SYMBOL} Price: {price}"

    alerts_list.append(first_msg)
    save_state()

    send_telegram(first_msg)

    while True:

        try:

            status, price = check_alerts()

            last_price = price
            last_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if status != last_status:

                if status == "BET-UP":
                    msg = f"BET ALERT UP | {SYMBOL} | Price: {price}"

                elif status == "BET-DOWN":
                    msg = f"BET ALERT DOWN | {SYMBOL} | Price: {price}"

                else:
                    msg = f"No Alert | {SYMBOL} | Price: {price}"

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
# Start Services
# ---------------------------
if __name__ == "__main__":

    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot_thread = Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    while True:
        time.sleep(60)
