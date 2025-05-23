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

class FeedPopulationRequest(BaseModel):
    feed_id: str
    topic: str  # NEW: selected topic from frontend
    num_initial_posts: int = 8  # Default number of initial posts
    num_comments_per_post: int = 8  # Default number of comments per post

@router.post("/populate-feed")
async def populate_feed(data: FeedPopulationRequest):
    try:
        # 1. Fetch the feed and its subject
        feed_resp = supabase.table("feeds").select("subject_id, global_prompt").eq("id", data.feed_id).single().execute()
        if not feed_resp.data:
            raise HTTPException(status_code=404, detail="Feed not found")
        
        feed = feed_resp.data
        subject_id = feed["subject_id"]
        global_prompt = feed.get("global_prompt", "")

        # 2. Fetch the subject
        subject_resp = supabase.table("subjects").select("name, general_prompt").eq("id", subject_id).single().execute()
        if not subject_resp.data:
            raise HTTPException(status_code=404, detail="Subject not found")
        
        subject = subject_resp.data

        # 3. Fetch personas for this subject
        personas_resp = supabase.table("personas").select("*").eq("subject_id", subject_id).execute()
        if not personas_resp.data:
            raise HTTPException(status_code=404, detail="No personas found for this subject")
        
        personas = personas_resp.data
        # Fallback: ensure all personas have a name
        for p in personas:
            if not p.get('name') or not p['name'].strip():
                p['name'] = f"Persona_{p.get('id', '')}"

        # Detect language from topic
        def detect_language(text):
            for c in text:
                if '\u0590' <= c <= '\u05FF':
                    return 'hebrew'
            return 'english'
        language = detect_language(data.topic)
        language_instruction = {
            'hebrew': 'כתוב את כל התגובה, כולל שם הדמות, בעברית. כתוב בסגנון פוסט או תגובה ברשת חברתית, כולל אימוג׳ים אם מתאים לדמות.',
            'english': 'Write your entire response, including the persona name, in English. Style it like a real social media post or comment, using emojis if it fits the character.'
        }[language]

        # 4. Generate initial posts
        posts = []
        for _ in range(data.num_initial_posts):
            post_persona = personas[_ % len(personas)]
            persona_name = post_persona.get('name', f"Persona_{post_persona.get('id','')}")
            persona_background = post_persona.get('prompt', '')
            post_prompt = (
                f"GLOBAL FEED PROMPT: {global_prompt}\n"
                f"You are {persona_name}, a historical or literary figure.\n"
                f"Topic: {data.topic}\n"
                f"Subject context: {subject['general_prompt']}\n"
                f"Persona background: {persona_background}\n\n"
                f"Write a believable, casual social media post (3-5 sentences) as if you are posting about your everyday life, events, or thoughts related to this topic. Do NOT just list keywords. Use first-person, make it engaging and authentic. If your character is quirky, use emojis and social media conventions. Do not use hashtags.\n"
                f"{language_instruction}"
            )
            post_content = model.generate_content(post_prompt).text.strip()
            
            # Create the post
            post = {
                "feed_id": data.feed_id,
                "author_id": post_persona["id"],
                "content": post_content,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Create a temporary user for the persona if it doesn't exist
            user_check = supabase.table("users").select("id").eq("id", post_persona["id"]).execute()
            if not user_check.data:
                temp_user = {
                    "id": post_persona["id"],
                    "username": post_persona["name"].lower().replace(" ", "_"),
                    "name": post_persona["name"],
                    "role": "student",
                    "password_hash": "$2b$10$ZHzvfUBiHM/Ldio6jlLdQuqLlR9egTi/HEOyb0Kttr/90Yj0df65W"  # Default hash
                }
                supabase.table("users").insert(temp_user).execute()
            
            post_resp = supabase.table("posts").insert(post).execute()
            if not post_resp.data:
                raise HTTPException(status_code=500, detail="Failed to create post")
            
            posts.append(post_resp.data[0])

        # 5. Generate comments for each post
        for post in posts:
            comment_personas = [p for p in personas if p["id"] != post["author_id"]]
            for i in range(data.num_comments_per_post):
                comment_persona = comment_personas[i % len(comment_personas)]
                comment_name = comment_persona.get('name', f"Persona_{comment_persona.get('id','')}")
                comment_background = comment_persona.get('prompt', '')
                comment_prompt = (
                    f"GLOBAL FEED PROMPT: {global_prompt}\n"
                    f"You are {comment_name}, a historical or literary figure.\n"
                    f"Topic: {data.topic}\n"
                    f"Subject context: {subject['general_prompt']}\n"
                    f"Persona background: {comment_background}\n\n"
                    f"Respond to this post by {post['author_id']} (content: {post['content']}) as if you are commenting on social media. Write a believable, casual, first-person comment (1-2 sentences) that adds to the conversation. If your character is quirky, use emojis and social media conventions. Do not use hashtags.\n"
                    f"{language_instruction}"
                )
                comment_content = model.generate_content(comment_prompt).text.strip()
                
                # Create the comment
                comment = {
                    "post_id": post["id"],
                    "author_id": comment_persona["id"],
                    "content": comment_content,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                comment_resp = supabase.table("comments").insert(comment).execute()
                if not comment_resp.data:
                    raise HTTPException(status_code=500, detail="Failed to create comment")

        return {
            "message": "Feed populated successfully",
            "posts_created": len(posts),
            "comments_created": len(posts) * data.num_comments_per_post,
            "topic_used": data.topic
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 