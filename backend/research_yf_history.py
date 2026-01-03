
import yfinance as yf
import pandas as pd

def check_history(symbol="RELIANCE.NS"):
    t = yf.Ticker(symbol)
    print(f"--- {symbol} Financials ---")
    
    # Quarterly Income Statement (for EPS/Net Income)
    q_inc = t.quarterly_income_stmt
    print("\nQuarterly Income Stmt (Columns = Dates?):")
    if q_inc is not None and not q_inc.empty:
        print(q_inc.columns)
        # Check rows for EPS
        print(q_inc.index[0:10])
    else:
        print("No quarterly income stmt found.")
        
    print("\n--- Shares Outstanding ---")
    # Balance sheet sometimes has SHARES_ISSUED
    q_bal = t.quarterly_balance_sheet
    if q_bal is not None and not q_bal.empty:
        print(q_bal.index[0:10])
    
    info = t.info
    print(f"\nCurrent Shares: {info.get('sharesOutstanding')}")

if __name__ == "__main__":
    check_history()
