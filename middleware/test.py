import requests
import json

def test_adk_service():
    """Simple test script for ADK service"""
    
    url = "http://localhost:8000/run"
    
    payload = {
        "app_name": "hope_updated",
        "user_id": "user1",
        "session_id": "session123",
        "new_message": {
            "parts": [
                {
                    "text": "please explain dad how to create gmail account"
                }
            ],
            "role": "user"
        },
        "streaming": False,
        "state_delta": {}
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    print("=== ADK SERVICE TEST ===")
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Headers: {headers}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("=" * 50)
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response URL: {response.url}")
        print("=" * 50)
        
        if response.status_code == 200:
            try:
                response_json = response.json()
                print("SUCCESS! Response JSON:")
                print(json.dumps(response_json, indent=2))
                
                # Extract final_response like in your main code
                final_response = "No response available"
                if isinstance(response_json, list) and len(response_json) > 0:
                    for item in response_json:
                        if isinstance(item, dict) and "actions" in item:
                            state_delta = item.get("actions", {}).get("stateDelta", {})
                            if "final_response" in state_delta:
                                final_response = state_delta["final_response"]
                                break
                
                print("=" * 50)
                print("EXTRACTED FINAL RESPONSE:")
                print(final_response)
                
            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON: {e}")
                print(f"Raw response: {response.text}")
                
        else:
            print(f"ERROR: HTTP {response.status_code}")
            print(f"Response text: {response.text}")
            
    except requests.exceptions.ConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
        print("Make sure ADK service is running on http://localhost:8000")
        
    except requests.exceptions.Timeout as e:
        print(f"TIMEOUT ERROR: {e}")
        
    except requests.exceptions.RequestException as e:
        print(f"REQUEST ERROR: {e}")
        
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_adk_service()