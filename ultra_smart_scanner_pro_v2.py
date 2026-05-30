import streamlit as st
import requests
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(layout="wide")
st.title("🚀 Ultra Smart Scanner PRO V2 (Hybrid Targets + Smart Risk)")

session = requests.Session()

# =========================
# 📦 COINS LIST
# =========================
@st.cache_data(ttl=3600)
def get_all_products():
    try:
        url = "https://api.exchange.coinbase.com/products"
        r = session.get(url, timeout=10).json()

        symbols = [
            item["base_currency"]
            for item in r
            if item.get("quote_currency") == "USD"
        ]

        return list(set(symbols))
    except Exception as e:
        st.error(f"Error loading coins: {e}")
        return []


# =========================
# 📊 MARKET DATA
# =========================
@st.cache_data(ttl=60)
def get_data(symbol):
    try:
        url = f"https://api.exchange.coinbase.com/products/{symbol}-USD/candles?granularity=3600"
        r = session.get(url, timeout=10).json()

        if not isinstance(r, list) or len(r) < 120:
            return None

        df = pd.DataFrame(r, columns=["time","low","high","open","close","volume"])
        df = df.dropna()

        if df.empty:
            return None

        df = df.sort_values("time").reset_index(drop=True)

        for col in ["low", "high", "open", "close", "volume"]:
            if col not in df.columns:
                return None

        return df.astype(float)

    except:
        return None


# =========================
# 📈 INDICATORS
# =========================
def add_indicators(df):

    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()

    delta = df["close"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    avg_gain = pd.Series(gain).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = pd.Series(loss).ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()

    df["macd"] = ema12 - ema26
    df["signal"] = df["macd"].ewm(span=9).mean()

    df["vol_ma"] = df["volume"].rolling(20).mean()
    df["support"] = df["low"].rolling(20).min()
    df["resistance"] = df["high"].rolling(20).max()

    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    df = df.dropna()
    return df


# =========================
# 🧠 SMART FILTER
# =========================
def smart_filter(df):

    required_cols = ["atr", "volume", "close", "ema50", "ema200", "rsi", "macd"]
    if any(col not in df.columns for col in required_cols):
        return False

    if df.isnull().any().any():
        return False

    if len(df) < 120:
        return False

    if (df["close"] <= 0).any():
        return False

    # dynamic volume filter (improved)
    if df["volume"].iloc[-1] < df["volume"].mean() * 0.5:
        return False

    volatility = df["atr"].iloc[-1] / (df["close"].mean() + 1e-9)

    if volatility < 0.01:
        return False

    return True


# =========================
# 🎯 ANALYSIS (SCORE)
# =========================
def analyze(df):

    latest = df.iloc[-1]
    score = 0

    if latest["rsi"] < 35:
        score += 15

    if latest["macd"] > latest["signal"]:
        score += 15

    if latest["ema50"] > latest["ema200"]:
        score += 15

    if latest["close"] <= latest["support"] * 1.02:
        score += 10

    if latest["volume"] > latest["vol_ma"]:
        score += 10

    if latest["atr"] > df["atr"].mean():
        score += 10

    if latest["close"] > df["close"].iloc[-5:].mean():
        score += 10

    trend_strength = df["close"].iloc[-10:].mean() > df["close"].iloc[-30:-10].mean()
    if trend_strength:
        score += 5

    signal = (
        "🔥 قوي جدًا" if score >= 80 else
        "🟢 فرصة" if score >= 65 else
        "⚠️ مراقبة" if score >= 50 else
        "❌ ضعيف"
    )

    return signal, score


# =========================
# 🛑 + 🎯 RISK MANAGEMENT (HYBRID TP)
# =========================
def risk_management(df):

    latest = df.iloc[-1]

    entry = latest["close"]
    atr = latest["atr"]
    resistance = latest["resistance"]

    if pd.isna(atr):
        return None

    # Stop Loss (ATR based)
    stop_loss = entry - (1.5 * atr)

    risk = entry - stop_loss

    # TP1 ATR-based
    tp1 = entry + (risk * 1)

    # TP2 RR-based
    tp2 = entry + (risk * 2)

    # TP3 resistance-based (hybrid smart exit)
    tp3 = resistance

    return entry, stop_loss, tp1, tp2, tp3


# =========================
# ⚙️ PROCESS COIN
# =========================
def process_coin(coin):

    df = get_data(coin)

    if df is None or df.empty:
        return None

    df = add_indicators(df)

    if not smart_filter(df):
        return None

    signal, score = analyze(df)

    if score < 50:
        return None

    risk = risk_management(df)
    if risk is None:
        return None

    entry, sl, tp1, tp2, tp3 = risk

    return {
        "Symbol": coin,
        "Signal": signal,
        "Score": score,
        "Entry": round(entry, 4),
        "Stop Loss": round(sl, 4),
        "TP1": round(tp1, 4),
        "TP2": round(tp2, 4),
        "TP3 (Resistance)": round(tp3, 4),
    }


# =========================
# 🚀 SCANNER
# =========================
results = []

if st.button("🚀 Scan Market PRO V2"):

    coins = get_all_products()

    if not coins:
        st.warning("No coins loaded")
        st.stop()

    progress = st.progress(0)

    with ThreadPoolExecutor(max_workers=10) as executor:

        for i, result in enumerate(executor.map(process_coin, coins)):

            if result:
                results.append(result)

            progress.progress((i + 1) / len(coins))

    if results:
        df_res = pd.DataFrame(results).sort_values("Score", ascending=False)
        st.success("🔥 Strong Clean Signals Found")
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("❌ No clean setups found")
