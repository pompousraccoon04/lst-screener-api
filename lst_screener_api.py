from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Tradier API Configuration
TRADIER_API_KEY = os.environ.get("TRADIER_API_KEY")
TRADIER_BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")

if not TRADIER_API_KEY:
    raise ValueError(
        "TRADIER_API_KEY environment variable is required. "
        "Create a .env file with: TRADIER_API_KEY=your_key_here"
    )

HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

# LST Strategy Stock Universe - 50 Blue Chip Stocks
LST_STOCK_UNIVERSE = {
    "consumer_staples": [
        "KO", "PEP", "WMT", "TGT", "COST", "KR", "PG", "CL", 
        "CLX", "KMB", "CHD", "MKC", "GIS", "K", "CPB"
    ],
    "healthcare": [
        "JNJ", "PFE", "ABBV", "UNH", "CVS", "MRK", "LLY", 
        "BMY", "AMGN", "GILD"
    ],
    "industrials": [
        "HD", "LOW", "MMM", "CAT", "DE", "UPS", "FDX", 
        "HON", "LMT", "RTX"
    ],
    "technology": [
        "AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "IBM", 
        "ORCL", "QCOM"
    ],
    "consumer_discretionary": [
        "MCD", "SBUX", "NKE", "DIS", "MAR", "BKNG", "CMG"
    ]
}

# Flatten universe for easy access
ALL_LST_STOCKS = [
    ticker for category in LST_STOCK_UNIVERSE.values() 
    for ticker in category
]


def get_stock_quote(ticker_symbol):
    """Get current stock quote from Tradier"""
    try:
        url = f"{TRADIER_BASE_URL}/markets/quotes"
        params = {"symbols": ticker_symbol}
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "quotes" in data and "quote" in data["quotes"]:
            quote = data["quotes"]["quote"]
            return {
                "price": float(quote.get("last", 0)),
                "volume": float(quote.get("volume", 0)),
                "description": quote.get("description", ""),
                "symbol": quote.get("symbol", ticker_symbol),
            }
        return None
    except Exception as e:
        print(f"Error fetching quote for {ticker_symbol}: {str(e)}")
        return None


def get_options_expirations(ticker_symbol):
    """Get available options expiration dates"""
    try:
        url = f"{TRADIER_BASE_URL}/markets/options/expirations"
        params = {"symbol": ticker_symbol}
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "expirations" in data and "date" in data["expirations"]:
            expirations = data["expirations"]["date"]
            if isinstance(expirations, str):
                expirations = [expirations]
            return expirations
        return []
    except Exception as e:
        print(f"Error fetching expirations for {ticker_symbol}: {str(e)}")
        return []


def find_lst_put_opportunities(ticker_symbol, current_price):
    """
    Find LST-compliant put options (delta 0.20-0.30, 30-45 DTE)
    
    Returns:
        List of opportunities with proper delta-based strikes
    """
    try:
        # Get expirations
        expirations = get_options_expirations(ticker_symbol)
        if not expirations:
            return []
        
        # Filter for 30-45 DTE (LST requirement - NO WEEKLIES!)
        target_date = datetime.now() + timedelta(days=30)
        end_date = datetime.now() + timedelta(days=45)
        
        suitable_expirations = []
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
            days_to_exp = (exp_date - datetime.now()).days
            if 30 <= days_to_exp <= 45:
                suitable_expirations.append({
                    "date": exp_str,
                    "dte": days_to_exp
                })
        
        if not suitable_expirations:
            print(f"  No suitable expirations (30-45 DTE) for {ticker_symbol}")
            return []
        
        opportunities = []
        
        # Check each suitable expiration
        for exp_info in suitable_expirations[:2]:  # Check first 2 suitable expirations
            exp_date = exp_info["date"]
            dte = exp_info["dte"]
            
            # Get options chain with Greeks
            url = f"{TRADIER_BASE_URL}/markets/options/chains"
            params = {
                "symbol": ticker_symbol,
                "expiration": exp_date,
                "greeks": "true"  # CRITICAL for delta
            }
            
            response = requests.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "options" not in data or "option" not in data["options"]:
                continue
            
            options = data["options"]["option"]
            if not isinstance(options, list):
                options = [options]
            
            # Filter for puts only
            puts = [opt for opt in options if opt.get("option_type") == "put"]
            
            # Find puts with delta between 0.20 and 0.30 (LST requirement)
            for put in puts:
                greeks = put.get("greeks", {})
                if not greeks or "delta" not in greeks:
                    continue
                
                delta = abs(float(greeks.get("delta", 0)))
                strike = float(put.get("strike", 0))
                bid = float(put.get("bid", 0))
                ask = float(put.get("ask", 0))
                mid_price = (bid + ask) / 2
                
                # LST CRITERIA: Delta 0.20-0.30
                if 0.20 <= delta <= 0.30:
                    # Calculate return metrics
                    capital_at_risk = strike * 100  # Per contract
                    premium_collected = mid_price * 100
                    return_pct = (premium_collected / capital_at_risk) * 100 if capital_at_risk > 0 else 0
                    
                    # Distance from current price
                    distance_pct = ((current_price - strike) / current_price) * 100
                    
                    # Check for reasonable liquidity
                    open_interest = int(put.get("open_interest", 0))
                    bid_ask_spread = ask - bid
                    
                    opportunities.append({
                        "expiration": exp_date,
                        "dte": dte,
                        "strike": round(strike, 2),
                        "delta": round(delta, 3),
                        "bid": round(bid, 2),
                        "ask": round(ask, 2),
                        "mid_price": round(mid_price, 2),
                        "premium_per_contract": round(premium_collected, 2),
                        "capital_at_risk": round(capital_at_risk, 2),
                        "return_pct": round(return_pct, 2),
                        "distance_from_price_pct": round(distance_pct, 2),
                        "open_interest": open_interest,
                        "bid_ask_spread": round(bid_ask_spread, 2),
                        "implied_volatility": round(float(greeks.get("mid_iv", 0)) * 100, 2)
                    })
        
        # Sort by return % descending
        opportunities.sort(key=lambda x: x["return_pct"], reverse=True)
        
        return opportunities
        
    except Exception as e:
        print(f"Error finding LST opportunities for {ticker_symbol}: {str(e)}")
        return []


def get_stock_iv(ticker_symbol, current_price):
    """
    Get average IV from 30-45 DTE options for stock qualification
    LST prefers lower IV (25-45%)
    """
    try:
        expirations = get_options_expirations(ticker_symbol)
        if not expirations:
            return None
        
        # Find 30-45 DTE expiration
        target_date = datetime.now() + timedelta(days=37)  # Middle of range
        
        closest_exp = None
        min_diff = float('inf')
        
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
            days_diff = (exp_date - datetime.now()).days
            
            if 30 <= days_diff <= 45:
                diff = abs(days_diff - 37)
                if diff < min_diff:
                    min_diff = diff
                    closest_exp = exp_str
        
        if not closest_exp:
            return None
        
        # Get options chain
        url = f"{TRADIER_BASE_URL}/markets/options/chains"
        params = {
            "symbol": ticker_symbol,
            "expiration": closest_exp,
            "greeks": "true"
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "options" not in data or "option" not in data["options"]:
            return None
        
        options = data["options"]["option"]
        if not isinstance(options, list):
            options = [options]
        
        # Get puts near ATM
        puts = [opt for opt in options if opt.get("option_type") == "put"]
        
        iv_values = []
        for put in puts:
            strike = float(put.get("strike", 0))
            greeks = put.get("greeks", {})
            
            # Look at strikes between 90-110% of current price
            if 0.90 * current_price <= strike <= 1.10 * current_price:
                if greeks and "mid_iv" in greeks:
                    mid_iv = float(greeks["mid_iv"])
                    if 0.05 <= mid_iv <= 2.0:  # Reasonable range
                        iv_values.append(mid_iv)
        
        if iv_values:
            avg_iv = sum(iv_values) / len(iv_values)
            return round(avg_iv * 100, 2)
        
        return None
        
    except Exception as e:
        print(f"Error getting IV for {ticker_symbol}: {str(e)}")
        return None


def screen_stock_for_lst(ticker_symbol):
    """
    Screen a single stock for LST strategy compliance
    
    LST Criteria:
    - Price: $50-200
    - Volume: 10M+ daily
    - IV: 25-45% (lower is better)
    - Must have delta 0.20-0.30 puts available
    """
    print(f"[LST] Screening {ticker_symbol}...")
    
    try:
        # Get quote
        quote = get_stock_quote(ticker_symbol)
        if not quote:
            return {
                "ticker": ticker_symbol,
                "qualified": False,
                "reason": "Unable to fetch quote"
            }
        
        price = quote["price"]
        volume_millions = quote["volume"] / 1_000_000
        
        # Check price range (LST: $50-200)
        if price < 50 or price > 200:
            return {
                "ticker": ticker_symbol,
                "qualified": False,
                "reason": f"Price ${price:.2f} outside LST range ($50-$200)",
                "price": round(price, 2),
                "volume_millions": round(volume_millions, 2)
            }
        
        # Check volume (LST: 10M+)
        if volume_millions < 10:
            return {
                "ticker": ticker_symbol,
                "qualified": False,
                "reason": f"Volume {volume_millions:.1f}M below LST minimum (10M)",
                "price": round(price, 2),
                "volume_millions": round(volume_millions, 2)
            }
        
        # Get IV
        iv = get_stock_iv(ticker_symbol, price)
        
        # Check IV range (LST: 25-45%)
        if iv is None:
            iv_status = "Unable to calculate IV"
            iv_qualified = False
        elif iv < 25:
            iv_status = f"IV {iv}% below LST minimum (25%)"
            iv_qualified = False
        elif iv > 45:
            iv_status = f"IV {iv}% above LST maximum (45%)"
            iv_qualified = False
        else:
            iv_status = f"IV {iv}% in LST range (25-45%)"
            iv_qualified = True
        
        # Find LST-compliant put opportunities
        opportunities = find_lst_put_opportunities(ticker_symbol, price)
        
        if not opportunities:
            return {
                "ticker": ticker_symbol,
                "qualified": False,
                "reason": "No delta 0.20-0.30 puts found in 30-45 DTE range",
                "price": round(price, 2),
                "volume_millions": round(volume_millions, 2),
                "iv": iv,
                "iv_status": iv_status
            }
        
        # Best opportunity (highest return)
        best_opp = opportunities[0]
        
        # Final qualification
        qualified = iv_qualified and len(opportunities) > 0
        
        result = {
            "ticker": ticker_symbol,
            "qualified": qualified,
            "price": round(price, 2),
            "volume_millions": round(volume_millions, 2),
            "iv": iv,
            "iv_status": iv_status,
            "description": quote["description"],
            "best_opportunity": best_opp,
            "total_opportunities": len(opportunities),
            "all_opportunities": opportunities[:5]  # Top 5
        }
        
        if qualified:
            print(f"  ✓ {ticker_symbol} QUALIFIED - ${price:.2f}, IV {iv}%, {len(opportunities)} opportunities")
        else:
            print(f"  ✗ {ticker_symbol} not qualified - {iv_status}")
        
        return result
        
    except Exception as e:
        print(f"Error screening {ticker_symbol}: {str(e)}")
        return {
            "ticker": ticker_symbol,
            "qualified": False,
            "reason": f"Error: {str(e)}"
        }


@app.route("/api/lst/universe", methods=["GET"])
def get_lst_universe():
    """
    Return the LST stock universe (50 blue chip stocks)
    """
    return jsonify({
        "success": True,
        "total_stocks": len(ALL_LST_STOCKS),
        "categories": LST_STOCK_UNIVERSE,
        "all_stocks": sorted(ALL_LST_STOCKS)
    })


@app.route("/api/lst/screen", methods=["GET", "POST"])
def lst_screen():
    """
    LST Strategy Screener
    
    Screen stocks for LST-compliant opportunities:
    - Delta 0.20-0.30 puts
    - 30-45 DTE (NO weeklies)
    - Blue chip stocks only
    - Price $50-200
    - Volume 10M+
    - IV 25-45%
    
    GET: ?tickers=KO,WMT or ?category=consumer_staples or ?all=true
    POST: {"tickers": ["KO", "WMT"]}
    """
    try:
        tickers_to_screen = []
        
        # Handle different request methods
        if request.method == "GET":
            # Option 1: Specific tickers
            tickers_param = request.args.get("tickers")
            if tickers_param:
                tickers_to_screen = [t.strip().upper() for t in tickers_param.split(",")]
            
            # Option 2: By category
            elif request.args.get("category"):
                category = request.args.get("category")
                if category in LST_STOCK_UNIVERSE:
                    tickers_to_screen = LST_STOCK_UNIVERSE[category]
                else:
                    return jsonify({
                        "error": f"Invalid category. Choose from: {list(LST_STOCK_UNIVERSE.keys())}"
                    }), 400
            
            # Option 3: All LST stocks
            elif request.args.get("all") == "true":
                tickers_to_screen = ALL_LST_STOCKS
            
            # Default: Top 10 consumer staples
            else:
                tickers_to_screen = LST_STOCK_UNIVERSE["consumer_staples"][:10]
        
        else:  # POST
            data = request.get_json()
            if not data or "tickers" not in data:
                return jsonify({
                    "error": "POST request must include 'tickers' list"
                }), 400
            tickers_to_screen = [t.upper() for t in data["tickers"]]
        
        if not tickers_to_screen:
            return jsonify({"error": "No tickers specified"}), 400
        
        print(f"\n[LST SCREENER] Processing {len(tickers_to_screen)} stocks...")
        
        # Screen each stock
        results = []
        qualified_count = 0
        
        for ticker in tickers_to_screen:
            result = screen_stock_for_lst(ticker)
            results.append(result)
            if result.get("qualified"):
                qualified_count += 1
        
        # Sort: qualified first, then by best return
        results.sort(
            key=lambda x: (
                x.get("qualified", False),
                x.get("best_opportunity", {}).get("return_pct", 0)
            ),
            reverse=True
        )
        
        print(f"\n[LST SCREENER] Complete: {qualified_count}/{len(results)} stocks qualified")
        
        return jsonify({
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "total_screened": len(results),
            "qualified": qualified_count,
            "strategy": "LST (Low Stress Trading)",
            "criteria": {
                "delta_range": "0.20-0.30",
                "dte_range": "30-45 days",
                "price_range": "$50-$200",
                "volume_minimum": "10M daily",
                "iv_range": "25-45%"
            },
            "results": results
        })
        
    except Exception as e:
        print(f"Error in LST screener: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "LST Options Screener API",
        "strategy": "Low Stress Trading (LST)",
        "data_source": "Tradier",
        "timestamp": datetime.now().isoformat()
    })


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  LST (Low Stress Trading) Options Screener API")
    print("="*60)
    print(f"  Strategy: Delta 0.20-0.30, 30-45 DTE")
    print(f"  Universe: 50 Blue Chip Stocks")
    print(f"  Target: 1% weekly, 98% win rate")
    print(f"  Data Source: Tradier API")
    print("="*60 + "\n")
    
    app.run(debug=True, host="0.0.0.0", port=5000)