from fastapi import FastAPI, HTTPException
import google.generativeai as genai
import os
from routes.ask import router as ask_router
from routes.feed import router as feed_router
from routes.feed_generation import router as feed_generation_router
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")
genai.configure(api_key=api_key)

# Initialize Gemini model
model = genai.GenerativeModel("gemini-pro")

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(supabase_url, supabase_key)

app = FastAPI()
app.include_router(ask_router)
app.include_router(feed_router)
app.include_router(feed_generation_router)

# Keep this route for user history tracking
@app.get("/history/{user_id}")
def get_history(user_id: str):
    response = supabase.table("interactions").select("*").eq("user_id", user_id).order("timestamp", desc=True).execute()
    return {"interactions": response.data}

