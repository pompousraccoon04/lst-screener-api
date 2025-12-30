#!/usr/bin/env python3
"""
Test script for LST Screener API

Usage:
    python test_api.py
"""

import requests
import json
from datetime import datetime

# API Base URL (change if deployed elsewhere)
BASE_URL = "http://localhost:5000"

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_health():
    """Test health check endpoint"""
    print_section("TEST 1: Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/api/health")
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200:
            print("✅ Health check passed!")
            return True
        else:
            print("❌ Health check failed!")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_universe():
    """Test LST universe endpoint"""
    print_section("TEST 2: LST Stock Universe")
    
    try:
        response = requests.get(f"{BASE_URL}/api/lst/universe")
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Total Stocks: {data.get('total_stocks')}")
        print(f"Categories: {list(data.get('categories', {}).keys())}")
        print(f"\nConsumer Staples ({len(data['categories']['consumer_staples'])} stocks):")
        print(f"  {', '.join(data['categories']['consumer_staples'])}")
        
        if response.status_code == 200:
            print("\n✅ Universe endpoint working!")
            return True
        else:
            print("\n❌ Universe endpoint failed!")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_screen_specific():
    """Test screening specific tickers"""
    print_section("TEST 3: Screen Specific Tickers (KO, WMT)")
    
    try:
        response = requests.get(f"{BASE_URL}/api/lst/screen?tickers=KO,WMT")
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Total Screened: {data.get('total_screened')}")
        print(f"Qualified: {data.get('qualified')}")
        
        # Show results
        for result in data.get('results', []):
            ticker = result['ticker']
            qualified = result['qualified']
            price = result.get('price', 'N/A')
            
            if qualified:
                best_opp = result['best_opportunity']
                print(f"\n✅ {ticker} - QUALIFIED")
                print(f"   Price: ${price}")
                print(f"   IV: {result.get('iv')}%")
                print(f"   Best Opportunity:")
                print(f"     Strike: ${best_opp['strike']}")
                print(f"     Delta: {best_opp['delta']}")
                print(f"     DTE: {best_opp['dte']} days")
                print(f"     Premium: ${best_opp['premium_per_contract']}")
                print(f"     Return: {best_opp['return_pct']}%")
                print(f"     Capital at Risk: ${best_opp['capital_at_risk']}")
            else:
                reason = result.get('reason', 'Unknown')
                print(f"\n❌ {ticker} - NOT QUALIFIED")
                print(f"   Reason: {reason}")
        
        if response.status_code == 200:
            print("\n✅ Screen specific tickers working!")
            return True
        else:
            print("\n❌ Screen failed!")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_screen_category():
    """Test screening by category"""
    print_section("TEST 4: Screen by Category (Consumer Staples - First 3)")
    
    try:
        # Get just 3 consumer staples for faster test
        response = requests.post(
            f"{BASE_URL}/api/lst/screen",
            json={"tickers": ["KO", "PEP", "WMT"]}
        )
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Total Screened: {data.get('total_screened')}")
        print(f"Qualified: {data.get('qualified')}")
        
        # Show summary
        qualified = [r['ticker'] for r in data.get('results', []) if r['qualified']]
        not_qualified = [r['ticker'] for r in data.get('results', []) if not r['qualified']]
        
        if qualified:
            print(f"\nQualified Stocks: {', '.join(qualified)}")
        if not_qualified:
            print(f"Not Qualified: {', '.join(not_qualified)}")
        
        if response.status_code == 200:
            print("\n✅ Category screening working!")
            return True
        else:
            print("\n❌ Category screening failed!")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("  LST SCREENER API TEST SUITE")
    print("="*60)
    print(f"  Testing API at: {BASE_URL}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    results = {
        "Health Check": test_health(),
        "Universe Endpoint": test_universe(),
        "Screen Specific Tickers": test_screen_specific(),
        "Screen by Category": test_screen_category()
    }
    
    print_section("TEST SUMMARY")
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! API is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check errors above.")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = run_all_tests()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        exit(1)
