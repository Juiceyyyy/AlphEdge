# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""User-operated Kite login token exchange. Run only on a trusted machine."""
import getpass
import hashlib
import os
from pathlib import Path
from urllib.parse import quote

import requests
from alpha_strategy.config import load_env


def main():
    load_env()
    key = os.getenv("KITE_API_KEY")
    secret = os.getenv("KITE_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Set KITE_API_KEY and KITE_API_SECRET in your local environment")
    print("Open this login URL in your own browser:")
    print(f"https://kite.zerodha.com/connect/login?v=3&api_key={quote(key)}")
    token = getpass.getpass("Paste the request_token from your configured redirect URL: ").strip()
    if not token:
        raise RuntimeError("No request token provided")
    checksum = hashlib.sha256((key + token + secret).encode()).hexdigest()
    response = requests.post("https://api.kite.trade/session/token",
        data={"api_key": key, "request_token": token, "checksum": checksum},
        headers={"X-Kite-Version": "3"}, timeout=20)
    response.raise_for_status()
    result = response.json()
    if result.get("status") != "success" or not result.get("data", {}).get("access_token"):
        raise RuntimeError("Broker did not return an access token")
    path = Path(os.getenv("BROKER_STATE_DIR", "var/broker")) / "access_token"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(result["data"]["access_token"])
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    print(f"Connected for today. Token saved locally in {path}; never commit or share it.")


if __name__ == "__main__":
    main()
