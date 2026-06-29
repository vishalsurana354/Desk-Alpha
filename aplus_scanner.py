#!/usr/bin/env python3
"""
A+ Setup Scanner – yfinance + Telegram
Runs on GitHub Actions, sends alerts to your phone.
"""

import yfinance as yf
import os
import requests
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIGURATION ============
# Read secrets from environment (set in GitHub Actions)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing Telegram secrets. Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.")

# Your universe (yfinance tickers)
UNIVERSE = {
    "Indian": [
        "TATAPOWER.NS", "COALINDIA.NS", "ONGC.NS", "RELIANCE.NS", "NTPC.NS",
        "POWERGRID.NS", "HDFCBANK.NS", "SBIN.NS", "ICICIBANK.NS", "AXISBANK.NS",
        "BAJFINANCE.NS", "CHOLAFIN.NS", "IOB.NS", "MAHABANK.NS", "HAL.NS",
        "BEL.NS", "MAZDOCK.NS", "DATAPATTNS.NS", "BDL.NS", "INFY.NS",
        "PERSISTENT.NS", "COFORGE.NS", "TRENT.NS", "EMAMILTD.NS", "DMART.NS",
        "TITAN.NS", "LODHA.NS", "GMDCLTD.NS", "HINDCOPPER.NS", "BHARTIARTL.NS",
        "TMCV.NS", "M&M.NS", "MARUTI.NS", "LT.NS", "SIEMENS.NS", "ABB.NS",
        "SUNPHARMA.NS", "DIVISLAB.NS", "LICHSGFIN.NS", "ADANIENT.NS", "ITC.NS",
        "DLF.NS", "ADANIPORTS.NS", "ADANIGREEN.NS"
    ],
    "US": [
        "IONQ", "QBTS", "RGTI", "QUBT", "IBM", "GOOGL", "MSFT", "AMZN",
        "NVDA", "AMD", "INTC", "AVGO", "CRM", "SNOW", "NFLX", "TSM",
        "META", "AAPL", "TSLA", "SNDK", "FCEL", "CRS", "STM", "MTRN",
        "NBIS", "BE", "DELL"
    ],
    "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD"],
    "Commodities": ["GC=F", "SI=F", "CL=F"]
}

# ============ HELPER FUNCTIONS ============

def get_data(ticker, interval, period):
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        return data if not data.empty else None
    except:
        return None

def detect_sweep(data, lookback=20):
    if data is None or len(data) < lookback:
        return None, None
    recent_high = data['High'].iloc[-lookback:-1].max()
    recent_low = data['Low'].iloc[-lookback:-1].min()
    last_high = data['High'].iloc[-1]
    last_low = data['Low'].iloc[-1]
    if last_high > recent_high:
        return "swept_high", recent_high
    elif last_low < recent_low:
        return "swept_low", recent_low
    return None, None

def detect_fvg(data, lookback=10):
    if data is None or len(data) < lookback:
        return None
    last = data.iloc[-1]
    prev = data.iloc[-2]
    avg_vol = data['Volume'].rolling(20).mean().iloc[-1]
    if last['Close'] > prev['High'] and last['Volume'] > avg_vol * 0.8:
        return "bullish_fvg"
    elif last['Close'] < prev['Low'] and last['Volume'] > avg_vol * 0.8:
        return "bearish_fvg"
    return None

def get_order_block(data):
    if data is None or len(data) < 5:
        return None
    return {
        "level": data['Close'].iloc[-3],
        "high": data['High'].iloc[-3],
        "low": data['Low'].iloc[-3]
    }

def get_fab4_territory(daily_data):
    if daily_data is None or len(daily_data) < 200:
        return "neutral"
    sma20 = daily_data['Close'].rolling(20).mean().iloc[-1]
    sma200 = daily_data['Close'].rolling(200).mean().iloc[-1]
    last = daily_data['Close'].iloc[-1]
    if last > sma20 and last > sma200:
        return "green"
    elif last < sma20 and last < sma200:
        return "red"
    return "no_mans_land"

def check_news_conflict(ticker):
    # Placeholder – add known high-impact dates if needed.
    return False

def calculate_rr(entry, stop, tp1):
    risk = abs(entry - stop)
    reward = abs(tp1 - entry)
    return reward / risk if risk > 0 else 0

def trend(data):
    if data is None or len(data) < 50:
        return "neutral"
    try:
        sma50 = data['Close'].rolling(50).mean().iloc[-1]
        close = data['Close'].iloc[-1]
        return "bullish" if close > sma50 else "bearish"
    except:
        return "neutral"

# ============ A+ SCORING ============

def score_aplus(ticker):
    details = {}
    score = 0
    reasons = []

    try:
        monthly = get_data(ticker, "1d", "6mo")
        weekly = get_data(ticker, "1wk", "3mo")
        daily = get_data(ticker, "1d", "2mo")
        fourh = get_data(ticker, "1h", "1mo")
        five = get_data(ticker, "5m", "5d")

        if any(x is None for x in [weekly, daily, fourh, five]):
            return 0, {"reason": "Insufficient data"}

        w_trend = trend(weekly)
        d_trend = trend(daily)
        h_trend = trend(fourh)

        # 1. Bias Alignment (Weekly + Daily + 4H)
        if w_trend == d_trend == h_trend and w_trend != "neutral":
            score += 2
            details["bias"] = f"{w_trend} aligned"
        else:
            reasons.append(f"Bias conflict: W={w_trend}, D={d_trend}, 4H={h_trend}")
            return score, {"score": score, "reasons": reasons, "details": details}

        # 2. Liquidity Sweep (5m)
        sweep_type, swept_level = detect_sweep(five)
        if sweep_type:
            score += 1.5
            details["sweep"] = f"{sweep_type} at {swept_level:.2f}"
        else:
            reasons.append("No liquidity sweep")

        # 3. Volume (≥1.5× avg)
        if five is not None and len(five) > 20:
            avg_vol = five['Volume'].rolling(20).mean().iloc[-1]
            last_vol = five['Volume'].iloc[-1]
            if last_vol >= 1.5 * avg_vol:
                score += 1.5
                details["volume"] = f"{last_vol/avg_vol:.1f}x avg"
            else:
                reasons.append(f"Volume {last_vol/avg_vol:.1f}x < 1.5x")
        else:
            reasons.append("Volume data insufficient")

        # 4. FVG (5m)
        fvg = detect_fvg(five)
        if fvg:
            score += 1
            details["fvg"] = fvg
        else:
            reasons.append("No FVG")

        # 5. Order Block (5m)
        ob = get_order_block(five)
        if ob:
            score += 1
            details["ob"] = f"{ob['level']:.2f}"
        else:
            reasons.append("No OB")

        # 6. Fab 4 Box (Daily)
        fab = get_fab4_territory(daily)
        if fab == "green" and (d_trend == "bullish" or h_trend == "bullish"):
            score += 1
            details["fab4"] = "green"
        elif fab == "red" and (d_trend == "bearish" or h_trend == "bearish"):
            score += 1
            details["fab4"] = "red"
        else:
            reasons.append(f"Fab4 {fab} wrong")

        # 7. R:R ≥ 1:2
        if sweep_type and swept_level is not None:
            current = five['Close'].iloc[-1]
            if sweep_type == "swept_low":  # bearish scenario
                entry = current
                stop = five['High'].iloc[-1] + (five['High'].iloc[-1] - swept_level) * 0.2
                tp1 = swept_level - (swept_level - five['Low'].iloc[-1]) * 0.5
                rr = calculate_rr(entry, stop, tp1)
                if rr >= 2:
                    score += 1
                    details["rr"] = f"{rr:.2f}"
                else:
                    reasons.append(f"R:R {rr:.2f} < 2")
            else:
                # bullish scenario – simplified
                pass
        else:
            reasons.append("No sweep for RR")

        # 8. News Conflict (mock)
        if not check_news_conflict(ticker):
            score += 1
            details["news"] = "clear"
        else:
            reasons.append("News conflict")

        # Bonus: Monthly bias alignment (adds 1 if aligned with daily)
        if monthly is not None and len(monthly) > 10:
            m_trend = trend(monthly)
            if m_trend == d_trend:
                score += 1
                details["monthly_bonus"] = "aligned"

        return score, {"score": score, "reasons": reasons, "details": details, "bias": d_trend}
    
    except Exception as e:
        print(f"Error scoring {ticker}: {str(e)}")
        return 0, {"reason": f"Error: {str(e)}"}

# ============ TELEGRAM ALERT ============

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        return requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10).ok
    except:
        return False

# ============ MAIN SCANNER ============

def scan_and_alert():
    alerts = []
    for sector, tickers in UNIVERSE.items():
        for ticker in tickers:
            print(f"Scanning {ticker}...")
            score, info = score_aplus(ticker)
            if score >= 8:
                d = info.get("details", {})
                try:
                    price_data = yf.download(ticker, period='1d', interval='1m', progress=False)
                    price = price_data['Close'].iloc[-1] if not price_data.empty else "N/A"
                except:
                    price = "N/A"
                
                msg = f"""🚨 <b>A+ SETUP ALERT</b> 🚨
<b>{ticker}</b> — Score: {score:.1f}/10
Direction: {info.get('bias', 'N/A')}
Current Price: {price}

✅ Checklist:
• Bias: {d.get('bias', 'N/A')}
• Sweep: {d.get('sweep', 'No')}
• Volume: {d.get('volume', 'N/A')}
• FVG: {d.get('fvg', 'No')}
• OB: {d.get('ob', 'N/A')}
• Fab4: {d.get('fab4', 'N/A')}
• R:R: {d.get('rr', 'N/A')}
• News: {d.get('news', 'N/A')}
• Monthly Bonus: {d.get('monthly_bonus', 'No')}

⚠️ Action: Wait for 5m candle confirmation.
"""
                alerts.append(msg)
    if alerts:
        full = "\n---\n".join(alerts)
        send_telegram(full)
        print("Alerts sent.")
    else:
        print("No A+ setups found.")

if __name__ == "__main__":
    scan_and_alert()
