import requests

API_BASE_URL = "http://localhost:8000"

def ask_character(user_id: str, character: str, message: str):
    url = f"{API_BASE_URL}/ask"
    payload = {
        "user_id": user_id,
        "character": character,
        "message": message
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("✅ Response:", response.json()["reply"])
        return response.json()
    else:
        print("❌ Error:", response.status_code, response.text)
        return None

def get_history(user_id: str):
    url = f"{API_BASE_URL}/history/{user_id}"
    response = requests.get(url)
    if response.status_code == 200:
        print(f"📚 History for {user_id}:")
        for i, entry in enumerate(response.json()["interactions"], start=1):
            print(f"\n--- Entry {i} ---")
            print("Question:", entry["message"])
            print("Reply:", entry["reply"])
        return response.json()["interactions"]
    else:
        print("❌ Error:", response.status_code, response.text)
        return []

# Example usage
if __name__ == "__main__":
    ask_character("frontend_tester", "Socrates", "What is virtue?")
    get_history("frontend_tester")