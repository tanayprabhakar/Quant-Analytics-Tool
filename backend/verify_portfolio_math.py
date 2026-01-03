
import requests
import json

def verify_risk_math():
    url = "http://localhost:8000/portfolio/analyze"
    payload = {
        "symbols": ["RELIANCE.NS", "TCS.NS", "INFY.NS"],
        "weights": [0.4, 0.3, 0.3],
        "start": "2024-01-01",
        "end": "2024-12-31",
        "benchmark": "^NSEI"
    }
    
    try:
        res = requests.post(url, json=payload)
        data = res.json()
        
        if "error" in data:
            print(f"Error: {data['error']}")
            return
            
        summary_vol = data['summary']['volatility']
        attribution = data['attribution']
        
        sum_risk_contrib = sum(item['risk_contribution'] for item in attribution)
        
        print(f"Portfolio Volatility: {summary_vol}")
        print(f"Sum of Risk Contribs: {sum_risk_contrib}")
        
        diff = abs(summary_vol - sum_risk_contrib)
        
        # We used annualized vol for both.
        # Check tolerance (rounding errors)
        if diff < 0.005:
            print("✅ PASS: Euler Attribution holds (Sum Risk Contrib ~= Volatility)")
        else:
            print(f"❌ FAIL: Discrepancy of {diff}")
            
    except Exception as e:
        print(f"Verification Failed: {e}")

if __name__ == "__main__":
    verify_risk_math()
