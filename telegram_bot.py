# -*- coding: utf-8 -*-
"""
===================================
Telegram Bot Interactive Trigger
===================================

This script runs a polling Telegram Bot listener.
When it receives a stock name/code (e.g. AAPL or /analyze AAPL) from Telegram,
it triggers the GitHub Actions workflow to run the analysis for that stock.
"""

import os
import re
import time
import subprocess
import requests
import sys

# Reconfigure stdout/stderr to use UTF-8 to prevent cp874 encoding errors on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding='utf-8')

# Load configurations
load_dotenv()

def get_github_token() -> str:
    """Retrieve GitHub Token dynamically from Git credentials or env."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
        
    try:
        # Ask local git credential manager
        p = subprocess.Popen(
            ["git", "credential", "fill"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, _ = p.communicate(input="protocol=https\nhost=github.com\n\n")
        for line in stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception as exc:
        print("⚠️ 无法从 Git 凭证管理器获取 Token:", exc)
        
    return ""

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = get_github_token()
REPO = "beenancy/daily_stock_analysis"

if not TELEGRAM_BOT_TOKEN:
    print("❌ 错误: 未在 .env 文件中检测到 TELEGRAM_BOT_TOKEN。请确保已在本地配置。")
    exit(1)

if not GITHUB_TOKEN:
    print("❌ 错误: 未检测到 GitHub Token。请在 .env 中配置 GITHUB_TOKEN，或确保本地 Git 已登录。")
    exit(1)

print("🚀 Telegram 互动机器人已启动 (Polling 模式)...")
print("📥 正在监听 Telegram 消息...")
print("💡 使用方式：在 Telegram 中发送股票代码（例如：AAPL 或 TSLA）或输入 /analyze AAPL")

offset = 0
while True:
    try:
        # Long poll for updates from Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
        response = requests.get(url, timeout=35).json()
        
        if not response.get("ok"):
            print("Telegram API 错误:", response)
            time.sleep(5)
            continue
            
        for update in response.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat = message.get("chat", {})
            text = message.get("text", "").strip()
            
            # Check authorization if chat_id is specified
            if TELEGRAM_CHAT_ID and str(chat.get("id")) != str(TELEGRAM_CHAT_ID):
                # Unrecognized user, skip
                continue
                
            if not text:
                continue
                
            stock = ""
            if text.startswith("/analyze "):
                stock = text.split(" ", 1)[1].strip().upper()
            elif text.startswith("/stock "):
                stock = text.split(" ", 1)[1].strip().upper()
            elif not text.startswith("/"):
                # If they send just a stock code like AAPL, NVDA, or 600519
                if re.match(r"^[A-Z0-9.\-]{2,10}$", text.upper()):
                    stock = text.upper()
                    
            if stock:
                print(f"📥 收到分析指令: {stock} (来自 Chat ID: {chat.get('id')})")
                
                # Send receipt confirmation to Telegram
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat["id"],
                        "text": f"📥 ได้รับคำสั่งวิเคราะห์หุ้น: *{stock}*\nกำลังส่งคำสั่งเพื่อรัน GitHub Actions..."
                    }
                )
                
                # Trigger GitHub Actions via API
                gh_url = f"https://api.github.com/repos/{REPO}/actions/workflows/00-daily-analysis.yml/dispatches"
                gh_headers = {
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
                gh_payload = {
                    "ref": "main",
                    "inputs": {
                        "mode": "stocks-only",  # Run stocks analysis only (quicker)
                        "force_run": True,
                        "stocks": stock
                    }
                }
                
                gh_resp = requests.post(gh_url, json=gh_payload, headers=gh_headers)
                
                if gh_resp.status_code == 204:
                    print(f"✅ 成功触发 GitHub Actions 运行 {stock}!")
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": chat["id"],
                            "text": (
                                f"✅ ส่งคำสั่งรันสำเร็จ!\n"
                                f"GitHub Actions กำลังดำเนินการวิเคราะห์หุ้น *{stock}* "
                                f"รายงานวิเคราะห์จะถูกส่งกลับเข้า Telegram นี้โดยอัตโนมัติเมื่อเสร็จสิ้น "
                                f"(ใช้เวลาประมาณ 1-3 นาที) ครับ 📊"
                            ),
                            "parse_mode": "Markdown"
                        }
                    )
                else:
                    print(f"❌ 触发 GitHub Actions 失败 (HTTP {gh_resp.status_code}): {gh_resp.text}")
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": chat["id"],
                            "text": f"❌ ไม่สามารถส่งรันบน GitHub ได้ (HTTP {gh_resp.status_code}):\n`{gh_resp.text[:200]}`",
                            "parse_mode": "Markdown"
                        }
                    )
                    
    except Exception as e:
        print("Error in polling loop:", e)
        time.sleep(5)
