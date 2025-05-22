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
        # Step 1: Get the latest relevant material for this character (you can change this filter logic)
        material_response = supabase.table("materials") \
            .select("key_points, content") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        if not material_response.data:
            raise HTTPException(status_code=404, detail="No material found for this character or topic")

        material = material_response.data[0]
        key_points = material["key_points"]
        full_content = material["content"]

        # Step 2: Build the first prompt using key points only
        key_points_prompt = (
            f"You are {request.character}, an expert historical or literary figure teaching students.\n"
            f"Your answers should be precise and grounded in the topic.\n"
            f"You may refer to trusted external knowledge only if it clearly aligns with the provided key points.\n\n"
            f"Key points from the topic:\n{key_points}\n\n"
            f"Student question:\n{request.message}\n\n"
            f"Respond in 3 to 5 clear sentences. Focus on clarity over depth.\n"
            f"If the key points are insufficient to answer accurately, say so clearly and avoid guessing."
        )

        response = model.generate_content(key_points_prompt)
        reply_text = response.text.strip()

        # Step 3: Fallback to full content if answer is weak
        if "not enough information" in reply_text.lower() or "i'm not sure" in reply_text.lower():
            full_prompt = (
                f"You are {request.character}, a knowledgeable figure.\n"
                f"Here is the full source material:\n{full_content}\n\n"
                f"Answer this student question as clearly and accurately as possible:\n{request.message}"
            )
            response = model.generate_content(full_prompt)
            reply_text = response.text.strip()

        # Step 4: Save to Supabase
        supabase.table("interactions").insert({
            "user_id": request.user_id,
            "character": request.character,
            "message": request.message,
            "reply": reply_text
        }).execute()

        return {"reply": reply_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# Get user's interactions
@app.get("/history/{user_id}")
def get_history(user_id: str):
    response = supabase.table("interactions").select("*").eq("user_id", user_id).order("timestamp", desc=True).execute()
    return {"interactions": response.data}

