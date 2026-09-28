#!/usr/bin/env python3
"""One-time helper: set the bot menu button to open your Mini App URL."""

import json
import os
import sys
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_telegram_menu.py https://your-domain.example/")
        sys.exit(1)

    web_app_url = sys.argv[1].rstrip("/") + "/"
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN in .env")
        sys.exit(1)

    payload = {
        "menu_button": {
            "type": "web_app",
            "text": "Lexical Hub",
            "web_app": {"url": web_app_url},
        }
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/setChatMenuButton",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())


if __name__ == "__main__":
    main()
