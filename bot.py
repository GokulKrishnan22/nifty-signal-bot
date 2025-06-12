import pandas as pd
import numpy as np
import datetime
import time
import yfinance as yf
import requests
import os

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "your_default_token")
CHAT_ID = os.getenv("CHAT_ID", "your_default_chat_id")
TICKER = "^NSEI"  # Use "^NSEBANK" for BankNifty

# === TELEGRAM ===
def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

# === DATA FETCH ===
def get_live_data():
    df = yf.download(tickers=TICKER, period="1d", interval="5m", auto_adjust=False, progress=False)
    df = df.reset_index()
    if df.empty or len(df) < 3:
        raise ValueError("📉 Not enough data to analyze!")
    return df

# === RSI ===
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# === INDICATORS ===
def calculate_indicators(df):
    df['EMA_9'] = df['Close'].ewm(span=9).mean()
    df['EMA_21'] = df['Close'].ewm(span=21).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    return df

# === CANDLE PATTERNS ===
def detect_candle(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    if latest['Close'] > latest['Open'] and prev['Close'] < prev['Open'] and latest['Open'] < prev['Close'] and latest['Close'] > prev['Open']:
        return "Bullish Engulfing"
    if latest['Close'] < latest['Open'] and prev['Close'] > prev['Open'] and latest['Open'] > prev['Close'] and latest['Close'] < prev['Open']:
        return "Bearish Engulfing"
    body = abs(latest['Close'] - latest['Open'])
    wick = latest['High'] - latest['Low']
    if body < wick * 0.3:
        return "Doji"
    return "No Pattern"

# === VOLUME TREND ===
def interpret_volume_trend(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    if latest['Close'] > prev['Close'] and latest['Volume'] > prev['Volume']:
        return "Strong Uptrend"
    if latest['Close'] > prev['Close'] and latest['Volume'] < prev['Volume']:
        return "Weak Uptrend"
    if latest['Close'] < prev['Close'] and latest['Volume'] > prev['Volume']:
        return "Strong Downtrend"
    if latest['Close'] < prev['Close'] and latest['Volume'] < prev['Volume']:
        return "Weak Downtrend"
    return "Neutral"

# === SUPPORT / RESISTANCE ===
def check_support_resistance(df):
    latest = df.iloc[-1]
    prev_low = df['Low'].iloc[-2]
    prev_high = df['High'].iloc[-2]
    close = latest['Close']
    if abs(close - prev_low) / close < 0.002:
        return "Near Support"
    elif abs(close - prev_high) / close < 0.002:
        return "Near Resistance"
    else:
        return "Middle Zone"

# === OPTION CHAIN BIAS ===
def get_option_chain_bias():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        res = session.get(url, headers=headers)
        data = res.json()

        ce_data = [d for d in data["records"]["data"] if 'CE' in d and d['CE'].get('openInterest', 0)]
        pe_data = [d for d in data["records"]["data"] if 'PE' in d and d['PE'].get('openInterest', 0)]

        top_ce = sorted(ce_data, key=lambda x: x['CE']['openInterest'], reverse=True)[0]
        top_pe = sorted(pe_data, key=lambda x: x['PE']['openInterest'], reverse=True)[0]

        ce_change = top_ce['CE']['changeinOpenInterest']
        pe_change = top_pe['PE']['changeinOpenInterest']

        if pe_change > ce_change:
            return "CALL Bias"
        elif ce_change > pe_change:
            return "PUT Bias"
        else:
            return "Neutral"
    except Exception as e:
        print("❌ Option chain fetch failed:", e)
        return "Neutral"

# === DECISION ENGINE ===
def decision_engine():
    df = get_live_data()
    df = calculate_indicators(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # Extract raw values
    close = float(latest['Close'])
    prev_close = float(prev['Close'])
    volume = float(latest['Volume'])
    prev_volume = float(prev['Volume'])
    ema_9 = float(latest['EMA_9'])
    ema_21 = float(latest['EMA_21'])

    # Individual conditions
    candle = detect_candle(df)
    sr_zone = check_support_resistance(df)
    option_bias = get_option_chain_bias()

    # Volume Trend (fix Series ambiguity)
    if close > prev_close and volume > prev_volume:
        vol_trend = "Strong Uptrend"
    elif close > prev_close and volume < prev_volume:
        vol_trend = "Weak Uptrend"
    elif close < prev_close and volume > prev_volume:
        vol_trend = "Strong Downtrend"
    elif close < prev_close and volume < prev_volume:
        vol_trend = "Weak Downtrend"
    else:
        vol_trend = "Neutral"

    # === Score Based System ===
    call_score = 0
    put_score = 0

    if vol_trend == "Strong Uptrend": call_score += 1
    if vol_trend == "Strong Downtrend": put_score += 1
    if candle == "Bullish Engulfing": call_score += 1
    if candle == "Bearish Engulfing": put_score += 1
    if sr_zone == "Near Support": call_score += 1
    if sr_zone == "Near Resistance": put_score += 1
    if option_bias == "CALL Bias": call_score += 1
    if option_bias == "PUT Bias": put_score += 1

    # === Final Signal Decision ===
    if call_score >= 2 and call_score > put_score:
        signal = "📈 *Suggestion: BUY CALL*"
    elif put_score >= 2 and put_score > call_score:
        signal = "📉 *Suggestion: BUY PUT*"
    else:
        signal = "⚖️ *Suggestion: NEUTRAL*"

    msg = (
        f"{signal}\n\n"
        f"📊 *Reasoning:*\n"
        f"• Candle: {candle}\n"
        f"• Volume Trend: {vol_trend}\n"
        f"• Zone: {sr_zone}\n"
        f"• Option Chain: {option_bias}\n"
        f"🕒 Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    print(msg)
    send_telegram_message(msg)


# === LOOP EVERY 5 MINUTES ===
while True:
    try:
        decision_engine()
    except Exception as e:
        print("⚠️ Error:", e)
    time.sleep(300)  # 5 minutes
