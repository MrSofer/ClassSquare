import requests
import json
import time

API_URL = "http://localhost:8000"

# Use existing IDs from your database
CLASS_ID = "84100220-dad4-4c1a-bf89-38693c7aab01"
SUBJECT_ID = "d7f5d600-8a41-4d0a-879f-a087f77a21f5"

# Choose a specific topic from the syllabus
TOPIC = "הקונגרס הציוני בבזל"

def test_generate_personas():
    print("Testing /generate-personas ...")
    resp = requests.post(
        f"{API_URL}/generate-personas",
        json={"subject_id": SUBJECT_ID, "count": 6, "topic": TOPIC}
    )
    print("Status:", resp.status_code)
    print("Response:", json.dumps(resp.json(), indent=2))
    personas = resp.json().get("personas", [])
    assert len(personas) > 0, "No personas returned"
    return personas

def test_generate_prompt(personas):
    print("\nTesting /generate-prompt ...")
    persona_names = [p["name"] for p in personas][:1]  # Use at least one persona name
    resp = requests.post(
        f"{API_URL}/generate-prompt",
        json={
            "subject_id": SUBJECT_ID,
            "class_id": CLASS_ID,
            "topic": TOPIC,
            "personas": persona_names
        }
    )
    print("Status:", resp.status_code)
    print("Response:", json.dumps(resp.json(), indent=2))
    prompt = resp.json().get("prompt")
    assert prompt, "No prompt returned"
    return prompt

def test_generate_feed(personas, prompt):
    print("\nTesting /generate-feed ...")
    # Pick personas for selected_personas
    selected_personas = personas
    # No manual personas, only generated ones
    data = {
        "class_id": CLASS_ID,
        "subject_id": SUBJECT_ID,
        "global_prompt": prompt,
        "topic": TOPIC,
        "selected_personas": selected_personas,
        "manual_personas": []
    }
    resp = requests.post(f"{API_URL}/generate-feed", json=data)
    print("Status:", resp.status_code)
    try:
        print("Response:", json.dumps(resp.json(), indent=2))
    except Exception:
        print("Raw response:", resp.text)
    assert resp.status_code == 200, "Feed creation failed"
    return resp.json()

if __name__ == "__main__":
    try:
        personas = test_generate_personas()
        prompt = test_generate_prompt(personas)
        test_generate_feed(personas, prompt)
    except Exception as e:
        print(f"Test failed: {e}")
        exit(1)