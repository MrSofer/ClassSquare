from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import google.generativeai as genai
import os
from supabase import create_client
from dotenv import load_dotenv
load_dotenv()

# Configure Gemini API
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")

genai.configure(api_key=api_key)

# Load Supabase credentials from environment variables or set them directly
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(supabase_url, supabase_key)

# Initialize Gemini model
model = genai.GenerativeModel("models/gemini-1.5-flash")

# Define FastAPI app
app = FastAPI()

# Request schema
class AskRequest(BaseModel):
    user_id: str
    character: str
    message: str

# POST /ask route
@app.post("/ask")
async def ask_character(request: AskRequest):
    try:
        prompt = f"You are {request.character}, a historical figure. Respond to this student question: {request.message}"
        response = model.generate_content(prompt)
        reply_text = response.text

        # Save to Supabase
        supabase.table("interactions").insert({
            "user_id": request.user_id,
            "character": request.character,
            "message": request.message,
            "reply": reply_text
        }).execute()

        return {"reply": reply_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/history/{user_id}")
def get_history(user_id: str):
    response = supabase.table("interactions").select("*").eq("user_id", user_id).order("timestamp", desc=True).execute()
    return {"interactions": response.data}