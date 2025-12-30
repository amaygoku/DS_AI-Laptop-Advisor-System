#!/usr/bin/env python3
"""
Quick test script to check if the recommendation API is working.
"""

import requests
import json

API_URL = "http://localhost:8000/chat"

def test_api():
    print("🔍 Testing Laptop Advisor API...")
    print(f"📡 API URL: {API_URL}\n")
    
    # Test query
    test_query = "Laptop gaming giá 25 triệu"
    
    print(f"📝 Test query: {test_query}")
    print("🔄 Sending request...\n")
    
    try:
        response = requests.post(
            API_URL,
            json={"text": test_query},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"✅ Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n📦 Response keys: {list(data.keys())}")
            
            recommendations = data.get("recommendations", [])
            print(f"📊 Recommendations count: {len(recommendations)}")
            
            if len(recommendations) > 0:
                print(f"\n✅ SUCCESS! Got {len(recommendations)} recommendations")
                print(f"\nFirst recommendation:")
                print(json.dumps(recommendations[0], indent=2, ensure_ascii=False))
            else:
                print(f"\n⚠️  WARNING: No recommendations returned!")
                print(f"\nFull response:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"\n❌ ERROR: Status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to API")
        print("Make sure the server is running:")
        print("   uvicorn src.api.main:app --port 8000")
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api()
