from flask import Flask, request
from threading import Thread
import time
import datetime
import json
import requests
import os

STATE_FILE = "state.json"

# ---------------------------
# Config
# ---------------------------
TOKEN = "8689386667:AAFhazRA-tWJK4_h5q7mlTNp5Z0J_gviGYk"
CHAT_ID = "8006267074"
SYMBOL = "BTCUSD-P"

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
# Flask app
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

# ---------------------------
# TradingView Webhook Endpoint
# ---------------------------
@app.route("/tv-webhook", methods=["POST"])
def tradingview_webhook():
    global last_price, last_time, alerts_list

    data = request.json
    if not data:
        return "No data received", 400

    action = data.get("action")  # Expected: "BUY" or "SELL"
    price = data.get("price", 0.0)
    symbol = data.get("symbol", SYMBOL)

    last_price = price
    last_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == "BUY":
        msg = f"📈 UP | {symbol} | {price}"
    elif action == "SELL":
        msg = f"📉 DOWN | {symbol} | {price}"
    else:
        msg = f"⏸ NO SIGNAL | {symbol} | {price}"

    print(msg)
    send_telegram(msg)

    alerts_list.append(msg)
    if len(alerts_list) > 50:
        alerts_list = alerts_list[-50:]
    save_state()

    return "ok", 200

# ---------------------------
# Run Flask
# ---------------------------
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ---------------------------
# Bot loop (optional for local testing)
# ---------------------------
def run_bot():
    while True:
        # This loop does nothing; all signals come via TradingView webhook
        time.sleep(60)

# ---------------------------
# Start Services
# ---------------------------
if __name__ == "__main__":
    Thread(target=run_flask).start()
    Thread(target=run_bot).start()
