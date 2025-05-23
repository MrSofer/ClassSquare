import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

# Test configuration
API_URL = "http://localhost:8000"  # Default FastAPI URL
TEST_FEED_ID = "your_feed_id_here"  # Replace with an actual feed ID from your database

def test_populate_feed():
    # Test data
    data = {
        "feed_id": TEST_FEED_ID,
        "num_initial_posts": 2,  # Using smaller numbers for testing
        "num_comments_per_post": 1
    }
    
    try:
        # Make the request
        response = requests.post(f"{API_URL}/populate-feed", json=data)
        
        # Print response details
        print(f"Status Code: {response.status_code}")
        print("Response:")
        print(json.dumps(response.json(), indent=2))
        
        # Basic validation
        if response.status_code == 200:
            result = response.json()
            print("\nTest Results:")
            print(f"✓ Posts created: {result['posts_created']}")
            print(f"✓ Comments created: {result['comments_created']}")
        else:
            print(f"❌ Error: {response.json().get('detail', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")

if __name__ == "__main__":
    test_populate_feed() 