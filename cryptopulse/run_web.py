"""
CryptoPulse Web UI entry point
"""
import sys
import os

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from cryptopulse.api.app import app
except ImportError as e:
    print(f"[CryptoPulse] Import failed: {e}")
    print("[CryptoPulse] Install deps: pip install flask pandas numpy loguru aiohttp websocket-client")
    sys.exit(1)

if __name__ == "__main__":
    print(f"[CryptoPulse] Web UI starting on http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=True)
