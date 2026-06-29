#!/usr/bin/env python3
"""
Telegram Webhook Handler for A+ Scanner
Receives messages and triggers GitHub Actions workflow
Supports individual stock triggers and market updates
"""

from flask import Flask, request
import os
import requests
import json
import hmac
import hashlib
import yfinance as yf

app = Flask(__name__)

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "vishalsurana354/desk-alpha"
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "your-secret-key")

# Stock universe
UNIVERSE = {
    "Indian": {
        "TATAPOWER.NS": "Tata Power",
        "COALINDIA.NS": "Coal India",
        "ONGC.NS": "ONGC",
        "RELIANCE.NS": "Reliance",
        "NTPC.NS": "NTPC",
        "POWERGRID.NS": "Power Grid",
        "HDFCBANK.NS": "HDFC Bank",
        "SBIN.NS": "SBI",
        "ICICIBANK.NS": "ICICI Bank",
        "AXISBANK.NS": "Axis Bank",
        "BAJFINANCE.NS": "Bajaj Finance",
        "CHOLAFIN.NS": "Chola Finance",
        "IOB.NS": "IOB",
        "MAHABANK.NS": "Maha Bank",
        "HAL.NS": "HAL",
        "BEL.NS": "BEL",
        "MAZDOCK.NS": "Mazagon Dock",
        "DATAPATTNS.NS": "Data Patterns",
        "BDL.NS": "BDL",
        "INFY.NS": "Infosys",
        "PERSISTENT.NS": "Persistent",
        "COFORGE.NS": "Coforge",
        "TRENT.NS": "Trent",
        "EMAMILTD.NS": "Emami",
        "DMART.NS": "D-Mart",
        "TITAN.NS": "Titan",
        "LODHA.NS": "Lodha",
        "GMDCLTD.NS": "GMDC",
        "HINDCOPPER.NS": "Hindustan Copper",
        "BHARTIARTL.NS": "Bharti Airtel",
        "TMCV.NS": "TMC",
        "M&M.NS": "M&M",
        "MARUTI.NS": "Maruti",
        "LT.NS": "L&T",
        "SIEMENS.NS": "Siemens",
        "ABB.NS": "ABB",
        "SUNPHARMA.NS": "Sun Pharma",
        "DIVISLAB.NS": "Divya Labs",
        "LICHSGFIN.NS": "Lich Fin",
        "ADANIENT.NS": "Adani Ent",
        "ITC.NS": "ITC",
        "DLF.NS": "DLF",
        "ADANIPORTS.NS": "Adani Ports",
        "ADANIGREEN.NS": "Adani Green"
    },
    "US": {
        "IONQ": "IonQ",
        "QBTS": "D-Wave",
        "RGTI": "Rigetti",
        "QUBT": "QubitTech",
        "IBM": "IBM",
        "GOOGL": "Google",
        "MSFT": "Microsoft",
        "AMZN": "Amazon",
        "NVDA": "NVIDIA",
        "AMD": "AMD",
        "INTC": "Intel",
        "AVGO": "Broadcom",
        "CRM": "Salesforce",
        "SNOW": "Snowflake",
        "NFLX": "Netflix",
        "TSM": "TSMC",
        "META": "Meta",
        "AAPL": "Apple",
        "TSLA": "Tesla",
        "SNDK": "SanDisk",
        "FCEL": "FuelCell",
        "CRS": "Corsair",
        "STM": "STMicro",
        "MTRN": "Materion",
        "NBIS": "NewBridger",
        "BE": "Berkshire",
        "DELL": "Dell"
    },
    "Crypto": {
        "BTC-USD": "Bitcoin",
        "ETH-USD": "Ethereum",
        "SOL-USD": "Solana",
        "ADA-USD": "Cardano"
    },
    "Commodities": {
        "GC=F": "Gold",
        "SI=F": "Silver",
        "CL=F": "Crude Oil",
        "XAU-USD": "Gold USD",
        "XAG-USD": "Silver USD"
    }
}

# Flatten all tickers for easy lookup
ALL_TICKERS = {}
for sector, stocks in UNIVERSE.items():
    ALL_TICKERS.update(stocks)

# ============ HELPER FUNCTIONS ============

def get_stock_price(ticker):
    """Get current stock price"""
    try:
        data = yf.download(ticker, period='1d', interval='1m', progress=False)
        if not data.empty:
            return data['Close'].iloc[-1]
    except:
        pass
    return None

def get_market_update():
    """Get market update for all major indices"""
    updates = []
    
    indices = {
        "^NSEI": "Nifty 50",
        "^BSESN": "BSE Sensex",
        "BTC-USD": "Bitcoin",
        "GC=F": "Gold",
    }
    
    for ticker, name in indices.items():
        try:
            data = yf.download(ticker, period='5d', progress=False)
            if not data.empty:
                close = data['Close'].iloc[-1]
                prev_close = data['Close'].iloc[-2] if len(data) > 1 else close
                change = ((close - prev_close) / prev_close) * 100
                symbol = "📈" if change > 0 else "📉"
                updates.append(f"{symbol} <b>{name}</b>: ${close:.2f} ({change:+.2f}%)")
        except:
            pass
    
    return "\n".join(updates) if updates else "Unable to fetch market data"

def trigger_github_workflow(stock_ticker=None):
    """Trigger GitHub Actions workflow"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/aplus-scanner.yml/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    data = {
        "ref": "main",
        "inputs": {
            "stock_ticker": stock_ticker or "ALL"
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        return response.status_code == 204
    except Exception as e:
        print(f"Error triggering workflow: {str(e)}")
        return False

def send_telegram_message(chat_id, message):
    """Send message back to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except:
        pass

def find_ticker(text):
    """Find matching ticker from user input"""
    text_lower = text.lower().strip()
    
    # Exact match
    for ticker, name in ALL_TICKERS.items():
        if text_lower == ticker.lower() or text_lower == name.lower():
            return ticker, name
    
    # Partial match
    for ticker, name in ALL_TICKERS.items():
        if text_lower in ticker.lower() or text_lower in name.lower():
            return ticker, name
    
    return None, None

# ============ WEBHOOK ROUTES ============

@app.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    """Receive Telegram webhook"""
    try:
        data = request.get_json()
        
        if not data:
            return {"ok": False}, 400
        
        # Extract message info
        if "message" not in data:
            return {"ok": True}, 200
        
        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        
        print(f"Received message from {chat_id}: {text}")
        
        # Check for trigger keywords
        if text.lower() in ["scan", "start", "trigger", "run", "go", "scan now", "/scan", "/start"]:
            # Trigger full scan
            if trigger_github_workflow():
                send_telegram_message(
                    chat_id,
                    "✅ <b>A+ Scanner Started!</b>\n\nScanning all stocks for A+ setups...\n\n📱 You'll receive alerts if any A+ setups are detected (score ≥ 8)."
                )
                print("Full workflow triggered successfully")
            else:
                send_telegram_message(
                    chat_id,
                    "❌ Error triggering scan. Please try again."
                )
        
        # Check for market update
        elif text.lower() in ["market", "update", "market update", "prices", "/market"]:
            update = get_market_update()
            send_telegram_message(
                chat_id,
                f"📊 <b>Market Update</b>\n\n{update}"
            )
        
        # Check for individual stock
        else:
            ticker, name = find_ticker(text)
            if ticker:
                price = get_stock_price(ticker)
                if price:
                    price_str = f"${price:.2f}" if "$" in ticker or "USD" in ticker else f"₹{price:.2f}"
                    send_telegram_message(
                        chat_id,
                        f"📈 <b>{name}</b> ({ticker})\nCurrent Price: {price_str}\n\nTriggering A+ scan for this stock..."
                    )
                    if trigger_github_workflow(ticker):
                        send_telegram_message(
                            chat_id,
                            f"✅ Scan started for <b>{name}</b>\n\nWaiting for A+ setup..."
                        )
                    else:
                        send_telegram_message(
                            chat_id,
                            "❌ Error triggering scan."
                        )
                else:
                    send_telegram_message(
                        chat_id,
                        f"⚠️ Could not fetch price for {name}"
                    )
            else:
                # Show help
                help_msg = """📊 <b>A+ Scanner Bot</b>

<b>Commands:</b>
• <code>scan</code> - Scan all stocks
• <code>market</code> - Market update
• <code>TICKER</code> - Scan specific stock

<b>Indian Stocks:</b>
TATAPOWER, RELIANCE, INFY, HDFCBANK, SBIN, etc.

<b>US Stocks:</b>
IBM, GOOGL, MSFT, AMZN, NVDA, AAPL, TSLA, etc.

<b>Crypto:</b>
BTC-USD, ETH-USD, SOL-USD

<b>Commodities:</b>
XAU-USD, XAG-USD, GC=F, SI=F, CL=F

<b>Examples:</b>
• <code>TATAPOWER.NS</code>
• <code>tata power</code>
• <code>GOOGL</code>
• <code>google</code>
• <code>BTC-USD</code>
• <code>bitcoin</code>
"""
                send_telegram_message(chat_id, help_msg)
        
        return {"ok": True}, 200
    
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return {"ok": False, "error": str(e)}, 500

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return {"status": "ok"}, 200

# ============ MAIN ============

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
