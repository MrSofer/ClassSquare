import requests

def test_ask(comment_id: str):
    response = requests.post("http://localhost:8000/ask", json={"comment_id": comment_id})
    print("Status:", response.status_code)
    print("Response:", response.json())

# Replace with your actual comment ID
test_ask("2792366d-4d15-4063-aa3e-3b219c7b4f3c")