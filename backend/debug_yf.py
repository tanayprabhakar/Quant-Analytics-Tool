import yfinance as yf
import json

try:
    tick = yf.Ticker("RELIANCE.NS")
    info = tick.info
    print(json.dumps(info, indent=2))
except Exception as e:
    print(f"Error: {e}")
