from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import google.generativeai as genai
from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

# Setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-1.5-flash")

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
router = APIRouter()

# Request schema
class AskByComment(BaseModel):
    comment_id: str

@router.post("/ask")
async def ask_by_comment(data: AskByComment):
    try:
        # 1. Fetch the comment
        comment_resp = supabase.table("comments").select("*").eq("id", data.comment_id).single().execute()
        if not comment_resp.data:
            raise HTTPException(status_code=404, detail="Comment not found.")
        comment = comment_resp.data
        post_id = comment["post_id"]
        parent_comment_id = comment.get("parent_comment_id")
        author_id = comment["author_id"]
        message = comment["content"]

        # 2. Fetch the post to get feed_id
        post_resp = supabase.table("posts").select("feed_id").eq("id", post_id).single().execute()
        if not post_resp.data or not post_resp.data["feed_id"]:
            raise HTTPException(status_code=404, detail="Post is missing a valid feed_id")
        feed_id = post_resp.data["feed_id"]

        # 3. Fetch the feed to get subject_id
        feed_resp = supabase.table("feeds").select("subject_id, global_prompt").eq("id", feed_id).single().execute()
        if not feed_resp.data or not feed_resp.data["subject_id"]:
            raise HTTPException(status_code=404, detail="Feed is missing a valid subject_id")
        subject_id = feed_resp.data["subject_id"]
        global_prompt = feed_resp.data.get("global_prompt", "")

        # 4. Fetch the subject
        subject_resp = supabase.table("subjects").select("name, general_prompt").eq("id", subject_id).single().execute()
        if not subject_resp.data:
            raise HTTPException(status_code=404, detail="Subject not found.")
        subject = subject_resp.data

        # 5. Determine the author to respond to (parent comment or post)
        if parent_comment_id:
            # Get the parent comment's author
            parent_resp = supabase.table("comments").select("author_id").eq("id", parent_comment_id).single().execute()
            if not parent_resp.data:
                raise HTTPException(status_code=404, detail="Parent comment not found.")
            target_author_id = parent_resp.data["author_id"]
        else:
            # No parent comment — use post author
            post_author_resp = supabase.table("posts").select("author_id").eq("id", post_id).single().execute()
            if not post_author_resp.data:
                raise HTTPException(status_code=404, detail="Post author not found.")
            target_author_id = post_author_resp.data["author_id"]

        # 6. Fetch personas for the subject
        personas_resp = supabase.table("personas").select("*").eq("subject_id", subject_id).execute()
        personas = personas_resp.data

        if not personas:
            raise HTTPException(status_code=404, detail=f"No personas found for subject_id {subject_id}")

        # 7. Pick a persona based on the parent comment author (not same as parent author)
        responding_persona = next((p for p in personas if p["id"] != target_author_id), None)
        if not responding_persona:
            raise HTTPException(status_code=404, detail="No suitable persona found to respond.")

        # 8. Fetch recent interactions for this user (if user is real)
        user_resp = supabase.table("users").select("name").eq("id", author_id).maybe_single().execute()
        username = user_resp.data["name"] if user_resp.data else "a participant"

        interactions_resp = supabase.table("interactions").select("message, reply") \
            .eq("user_id", author_id).order("timestamp", desc=True).limit(3).execute()

        interaction_history = "\n".join(
            [f"Q: {i['message']}\nA: {i['reply']}" for i in interactions_resp.data]
        ) if interactions_resp.data else ""

        # 9. Build the prompt
        prompt = (
            f"You are {responding_persona['name']}, a historical or literary figure.\n"
            f"Topic: {subject['name']}\n"
            f"Subject context: {subject['general_prompt']}\n\n"
        )

        if responding_persona.get("prompt"):
            prompt += f"Persona background: {responding_persona['prompt']}\n\n"

        if interaction_history:
            prompt += f"Here are some recent things {username} has asked or discussed:\n{interaction_history}\n\n"

        prompt += f"Now respond to this message:\n{message}\n\n"
        prompt += f"Respond as {responding_persona['name']} would, keeping a consistent tone and voice."

        # 10. Generate response
        response = model.generate_content(prompt)
        reply_text = response.text.strip()

        # 11. Save the new comment
        new_comment = {
            "post_id": post_id,
            "parent_comment_id": data.comment_id,
            "author_id": responding_persona["id"],
            "content": reply_text,
            "created_at": datetime.utcnow().isoformat()
        }

        supabase.table("comments").insert(new_comment).execute()

        return {"reply": reply_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))