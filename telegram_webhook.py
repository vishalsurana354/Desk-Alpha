#!/usr/bin/env python3
"""
Telegram Webhook Handler for A+ Scanner
Receives messages and triggers GitHub Actions workflow
"""

from flask import Flask, request
import os
import requests
import json
import hmac
import hashlib

app = Flask(__name__)

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "vishalsurana354/desk-alpha"
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "your-secret-key")

# ============ HELPER FUNCTIONS ============

def verify_telegram_signature(body, signature):
    """Verify Telegram webhook signature"""
    expected_sig = hmac.new(
        TELEGRAM_TOKEN.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_sig)

def trigger_github_workflow():
    """Trigger GitHub Actions workflow"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/aplus-scanner.yml/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    data = {
        "ref": "main"
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
        text = message.get("text", "").lower().strip()
        
        print(f"Received message from {chat_id}: {text}")
        
        # Check for trigger keywords
        trigger_keywords = ["scan", "start", "trigger", "run", "go", "scan now"]
        
        if any(keyword in text for keyword in trigger_keywords):
            # Trigger workflow
            if trigger_github_workflow():
                send_telegram_message(
                    chat_id,
                    "✅ A+ Scanner triggered! Scan will start in a few seconds.\n\nCheck your alerts for any A+ setups detected."
                )
                print("Workflow triggered successfully")
            else:
                send_telegram_message(
                    chat_id,
                    "❌ Error triggering scan. Please try again."
                )
                print("Failed to trigger workflow")
        else:
            send_telegram_message(
                chat_id,
                "📊 A+ Scanner Bot\n\nSend any of these commands to trigger a scan:\n• /scan\n• scan\n• start\n• trigger\n• run"
            )
        
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
