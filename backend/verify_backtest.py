import requests
import sys
import numpy as np

URL = "http://localhost:8000/india/backtest/momentum?lookback_days=90&top_n=10"

def verify():
    print(f"Testing {URL}...")
    
    # 1. First Run
    resp1 = requests.get(URL)
    if resp1.status_code != 200:
        print(f"FAILED: Initial request failed with {resp1.status_code}")
        sys.exit(1)
        
    data1 = resp1.json()
    metrics1 = data1["metrics"]
    curve1 = data1["equity_curve"]
    
    print("Run 1 Metrics:", metrics1)
    
    # 2. logical Sanity Checks
    print("\nVerifying Logic:")
    
    # Max Drawdown must be <= 0
    if metrics1["max_drawdown"] > 0:
        print(f"FAILED: Max drawdown {metrics1['max_drawdown']} > 0")
        sys.exit(1)
    else:
        print(" - Max Drawdown check passed")
        
    # Trading days should be reasonable (>0)
    if metrics1["trading_days"] <= 0:
        print(f"FAILED: Trading days {metrics1['trading_days']} <= 0")
        sys.exit(1)
    else:
        print(" - Trading days check passed")
        
    # Equity curve sanity
    start_val = curve1[0]["value"]
    if abs(start_val - 1.0) > 0.0001:
         print(f"FAILED: Equity curve must start at 1.0, got {start_val}")
         sys.exit(1)
    else:
        print(" - Equity curve start check passed")
         
    # 3. Reproducibility Check
    print("\nVerifying Reproducibility (Run 2)...")
    resp2 = requests.get(URL)
    data2 = resp2.json()
    metrics2 = data2["metrics"]
    curve2 = data2["equity_curve"]
    
    if metrics1 != metrics2:
        print("FAILED: Metrics differ between runs!")
        print("Run 1:", metrics1)
        print("Run 2:", metrics2)
        sys.exit(1)
        
    if len(curve1) != len(curve2):
         print("FAILED: Equity curve length matches")
         sys.exit(1)
         
    # Check exact values
    for i in range(len(curve1)):
        v1 = curve1[i]["value"]
        v2 = curve2[i]["value"]
        if abs(v1 - v2) > 1e-9:
             print(f"FAILED: Curve mismatch at {curve1[i]['date']}: {v1} vs {v2}")
             sys.exit(1)
             
    print(" - Reproducibility check passed (exact match)")
    print("\nALL BACKTEST CHECKS PASSED")

if __name__ == "__main__":
    verify()
