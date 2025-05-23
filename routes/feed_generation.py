from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
import google.generativeai as genai
from supabase import create_client
import os
from dotenv import load_dotenv
import yaml
from langchain.prompts import PromptTemplate
import random
import uuid
import json
from typing import Optional, List, Dict
import time
load_dotenv()

# Setup
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-2.0-flash")

router = APIRouter()

class PersonaIn(BaseModel):
    name: str
    prompt: str
    id: str | None = None

    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        if self.id:
            d['id'] = self.id
        return d

class GenerateFeedRequest(BaseModel):
    class_id: str
    subject_id: str
    global_prompt: str
    topic: str
    selected_personas: list[PersonaIn] = Field(..., min_items=3)
    manual_personas: list[PersonaIn] = []

class GeneratePersonasRequest(BaseModel):
    subject_id: str
    count: int = 15
    topic: str

class GeneratePromptRequest(BaseModel):
    subject_id: str
    class_id: str
    topic: str
    personas: list[str] = Field(..., min_items=1)

class SubjectIn(BaseModel):
    name: str
    description: str
    syllabus: str

@router.post("/generate-feed")
async def generate_feed(data: GenerateFeedRequest):
    # 1. Validate class, subject
    class_resp = supabase.table("classes").select("id").eq("id", data.class_id).single().execute()
    if not class_resp.data:
        raise HTTPException(status_code=404, detail="Class not found")
    subject_resp = supabase.table("subjects").select("id, syllabus, name").eq("id", data.subject_id).single().execute()
    if not subject_resp.data:
        raise HTTPException(status_code=404, detail="Subject not found")
    subject = subject_resp.data
    topic = data.topic
    def detect_language(text):
        for c in text:
            if '\u0590' <= c <= '\u05FF':
                return 'hebrew'
        return 'english'
    language = detect_language(topic)
    language_instruction = {
        'hebrew': 'כתוב את התגובה בעברית בלבד, בסגנון פוסט או תגובה ברשת חברתית, ללא התחלה בשם הדמות. כתוב רק את התוכן כאילו אתה הדמות, אל תציין את שמך בתחילת הפוסט או התגובה.',
        'english': 'Write your response in English only, styled like a real social media post or comment, but do NOT start with your name. Write only the content as if you are the persona, do not mention your name at the beginning.'
    }[language]
    # 2. Save personas (selected + manual)
    all_personas = data.selected_personas + data.manual_personas
    persona_ids = []
    for persona in all_personas:
        if hasattr(persona, 'dict'):
            persona_dict = persona.dict()
        else:
            persona_dict = persona
        existing = supabase.table("personas").select("id").eq("subject_id", data.subject_id).eq("name", persona_dict['name']).maybe_single().execute()
        if existing and existing.data:
            persona_id = existing.data["id"]
        else:
            insert = {
                "subject_id": data.subject_id,
                "name": persona_dict['name'],
                "prompt": persona_dict['prompt']
            }
            resp = supabase.table("personas").insert(insert).execute()
            if not resp.data:
                raise HTTPException(status_code=500, detail=f"Failed to save persona {persona_dict['name']}")
            persona_id = resp.data[0]["id"]
        if hasattr(persona, 'dict'):
            persona.id = persona_id
        else:
            persona['id'] = persona_id
        persona_ids.append(persona_id)
        
        # Create user for persona if it doesn't exist
        user_check = supabase.table("users").select("id").eq("id", persona_id).maybe_single().execute()
        if not user_check or not user_check.data:
            # Create a unique username by adding a timestamp
            timestamp = int(time.time())
            base_username = persona_dict['name'].lower().replace(" ", "_")
            username = f"{base_username}_{timestamp}"
            
            temp_user = {
                "id": persona_id,
                "username": username,
                "name": persona_dict['name'],
                "role": "student",
                "password_hash": "$2b$10$ZHzvfUBiHM/Ldio6jlLdQuqLlR9egTi/HEOyb0Kttr/90Yj0df65W"
            }
            try:
                resp = supabase.table("users").insert(temp_user).execute()
                if not resp.data:
                    raise HTTPException(status_code=500, detail=f"Failed to create user for persona {persona_dict['name']}")
            except Exception as e:
                print(f"Error creating user: {e}")
                # If user creation fails, we can't proceed
                raise HTTPException(status_code=500, detail=f"Failed to create user for persona {persona_dict['name']}")

    # 3. Create the feed
    feed = {
        "subject_id": data.subject_id,
        "title": topic,
        "global_prompt": data.global_prompt
    }
    feed_resp = supabase.table("feeds").insert(feed).execute()
    if not feed_resp.data:
        raise HTTPException(status_code=500, detail="Failed to create feed")
    feed_id = feed_resp.data[0]["id"]
    
    # 4. Populate the feed with posts/comments using all personas for the subject and the selected topic
    all_personas = data.selected_personas + data.manual_personas
    if not all_personas or len(all_personas) < 3:
        raise HTTPException(status_code=400, detail="Not enough personas to populate feed")
    num_personas = min(len(all_personas), random.randint(6, 12))
    selected_personas = random.sample(all_personas, num_personas)
    posts = []
    num_posts = min(len(selected_personas), 5)
    for i in range(num_posts):
        post_persona = selected_personas[i % len(selected_personas)]
        if hasattr(post_persona, 'dict'):
            post_persona = post_persona.dict()
        persona_name = post_persona.get('name', f"Persona_{post_persona.get('id','')}")
        persona_background = post_persona.get('prompt', '')
        post_prompt = (
            f"GLOBAL FEED PROMPT: {data.global_prompt}\n"
            f"You are {persona_name}, a real historical figure.\n"
            f"Topic: {topic}\n"
            f"Persona background: {persona_background}\n\n"
            f"Write a post of 3-5 sentences about a real historical event related to this topic. Express emotion, humanity, and your unique perspective. Let your feelings, doubts, hopes, or excitement show through your words. Make sure your writing style fits your character and the time period. Do not use emojis or modern slang. Keep it authentic and historically accurate. Do NOT start with your name; write only the content as if you are the persona.\n"
            f"{language_instruction}"
        )
        post_prompt_template = PromptTemplate(input_variables=["global_prompt", "persona_name", "topic", "persona_background", "language_instruction"], template=post_prompt)
        formatted_post_prompt = post_prompt_template.format(
            global_prompt=data.global_prompt,
            persona_name=persona_name,
            topic=topic,
            persona_background=persona_background,
            language_instruction=language_instruction
        )
        post_content = model.generate_content(formatted_post_prompt).text.strip()
        post = {
            "feed_id": feed_id,
            "author_id": post_persona["id"],
            "content": post_content,
            "created_at": datetime.utcnow().isoformat()
        }
        post_resp = supabase.table("posts").insert(post).execute()
        if not post_resp.data:
            raise HTTPException(status_code=500, detail="Failed to create post")
        posts.append(post_resp.data[0])
    for post in posts:
        comment_personas = []
        for p in selected_personas:
            if hasattr(p, 'dict'):
                p = p.dict()
            if p["id"] != post["author_id"]:
                comment_personas.append(p)
        for i in range(min(2, len(comment_personas))):
            comment_persona = comment_personas[i % len(comment_personas)]
            comment_name = comment_persona.get('name', f"Persona_{comment_persona.get('id','')}")
            comment_background = comment_persona.get('prompt', '')
            comment_prompt = (
                f"GLOBAL FEED PROMPT: {data.global_prompt}\n"
                f"You are {comment_name}, a real historical figure.\n"
                f"Topic: {topic}\n"
                f"Persona background: {comment_background}\n\n"
                f"Respond to this post by {post['author_id']} (content: {post['content']}) as if you are {comment_name}. If you historically disagreed or argued with the post author, express that. Do not use emojis or modern slang. Write a short, first-person comment (2-3 sentences). Do NOT start with your name; write only the content as if you are the persona.\n"
                f"{language_instruction}"
            )
            comment_prompt_template = PromptTemplate(input_variables=["global_prompt", "comment_name", "topic", "comment_background", "author_id", "post_content", "language_instruction"], template=comment_prompt)
            formatted_comment_prompt = comment_prompt_template.format(
                global_prompt=data.global_prompt,
                comment_name=comment_name,
                topic=topic,
                comment_background=comment_background,
                author_id=post['author_id'],
                post_content=post['content'],
                language_instruction=language_instruction
            )
            comment_content = model.generate_content(formatted_comment_prompt).text.strip()
            comment = {
                "post_id": post["id"],
                "author_id": comment_persona["id"],
                "content": comment_content,
                "created_at": datetime.utcnow().isoformat()
            }
            supabase.table("comments").insert(comment).execute()
    return {
        "feed_id": feed_id,
        "posts_created": len(posts),
        "personas_used": [p.name if hasattr(p, 'name') else p['name'] for p in selected_personas],
        "topic_used": topic,
        "message": "Feed created and populated successfully."
    }

@router.post("/generate-personas")
async def generate_personas(data: GeneratePersonasRequest):
    try:
        subject_resp = supabase.table("subjects").select("name").eq("id", data.subject_id).single().execute()
        subject_name = subject_resp.data["name"] if subject_resp.data else "the subject"
    except Exception as e:
        print(f"Warning: Could not fetch subject: {e}")
        subject_name = "the subject"
    persona_topic = data.topic
    print(f"Persona topic: {persona_topic}")
    def detect_language(text):
        for c in text:
            if '\u0590' <= c <= '\u05FF':
                return 'hebrew'
        return 'english'
    language = detect_language(persona_topic)
    persona_language_instruction = {
        'hebrew': f"ציין {data.count} דמויות היסטוריות אמיתיות ורלוונטיות שהיו קשורות ישירות לנושא '{persona_topic}'. עבור כל דמות, כתוב שם מלא ומשפט רקע קצר על פועלה או עמדתה בנושא. אל תמציא דמויות. אל תוסיף דמויות שאינן קשורות ישירות לנושא. החזר אך ורק רשימת YAML של מילונים, כל אחד עם המפתחות 'name' ו-'prompt', ללא מספור, עיצוב markdown, קוד בלוק (ללא ```yaml או ```), כותרות, או מפתחות נוספים. חשוב: כל הדמויות חייבות להיות אמיתיות ולא מומצאות. ודא שכל שם הוא של דמות היסטורית מוכרת, או של אדם אמיתי בלבד. אל תכלול דמויות בדיוניות, דמויות מספרות, או שמות שאינם קיימים במציאות. אל תחזור על דמויות שהוזכרו בעבר, ונסה להעדיף דמויות פחות מוכרות או פחות מוזכרות, כל עוד הן רלוונטיות לנושא.",
        'english': f"List {data.count} real, relevant historical figures directly related to the topic '{persona_topic}'. For each, provide the full name and a short background sentence about their role or stance on the topic. Do not invent personas. Do not include figures not directly relevant to the topic. Output ONLY a YAML list of dictionaries, each with 'name' and 'prompt' keys, and nothing else. Do NOT include numbering, markdown styling, code blocks (no ```yaml or ```), headers, or extra keys. Important: All characters must be real and not invented. Ensure every name is a well-known historical figure or a real person only. Do not include fictional characters, book/movie/game characters, or made-up names. Do not repeat characters you have already mentioned in previous generations. Prioritize lesser-known or less frequently mentioned real historical figures relevant to the topic. Avoid always listing the most famous figures first."
    }[language]
    persona_prompt_template = PromptTemplate(
        input_variables=["count", "persona_topic"],
        template=persona_language_instruction
    )
    max_retries = 3
    personas = []
    for attempt in range(max_retries):
        persona_prompt = persona_prompt_template.format(count=data.count, persona_topic=persona_topic)
        print(f"Generating personas with Gemini API... (attempt {attempt+1})")
        result = model.generate_content(persona_prompt).text.strip()
        if result.startswith('```yaml'):
            result = result[len('```yaml'):].strip()
        if result.startswith('```'):
            result = result[len('```'):].strip()
        if result.endswith('```'):
            result = result[:-3].strip()
        lines = result.split('\n')
        start_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('-') or line.strip().startswith('{'):
                start_idx = i
                break
        filtered_result = '\n'.join(lines[start_idx:])
        print(f"Filtered result for YAML parsing:\n{filtered_result}")
        try:
            yaml_data = yaml.safe_load(filtered_result)
            if isinstance(yaml_data, dict):
                for key in ["personas", "דמויות", "characters", "list"]:
                    if key in yaml_data and isinstance(yaml_data[key], list):
                        yaml_data = yaml_data[key]
                        break
            if isinstance(yaml_data, list):
                for item in yaml_data:
                    if isinstance(item, dict) and 'name' in item and 'prompt' in item:
                        personas.append({"name": item['name'].strip(), "prompt": item['prompt'].strip()})
            else:
                for line in filtered_result.split('\n'):
                    if not line.strip():
                        continue
                    if ':' in line:
                        name, prompt = line.split(':', 1)
                        personas.append({"name": name.strip(), "prompt": prompt.strip()})
                    elif '-' in line:
                        name, prompt = line.split('-', 1)
                        personas.append({"name": name.strip(), "prompt": prompt.strip()})
                    else:
                        personas.append({"name": line.strip(), "prompt": ""})
        except Exception as e:
            print(f"Error parsing YAML: {e}")
            for line in filtered_result.split('\n'):
                if not line.strip():
                    continue
                if ':' in line:
                    name, prompt = line.split(':', 1)
                    personas.append({"name": name.strip(), "prompt": prompt.strip()})
                elif '-' in line:
                    name, prompt = line.split('-', 1)
                    personas.append({"name": name.strip(), "prompt": prompt.strip()})
                else:
                    personas.append({"name": line.strip(), "prompt": ""})
        personas = [p for p in personas if p['name'] and p['prompt']]
        if len(personas) >= data.count:
            break
        else:
            print(f"Retrying persona generation, only got {len(personas)} valid personas.")
            personas = []
    print("Personas generated successfully.")
    saved_personas = []
    for persona in personas:
        existing = supabase.table("personas").select("id").eq("subject_id", data.subject_id).eq("name", persona['name']).maybe_single().execute()
        if existing and existing.data:
            persona_id = existing.data["id"]
        else:
            insert = {
                "subject_id": data.subject_id,
                "name": persona['name'],
                "prompt": persona['prompt']
            }
            resp = supabase.table("personas").insert(insert).execute()
            if not resp.data:
                raise HTTPException(status_code=500, detail=f"Failed to save persona {persona['name']}")
            persona_id = resp.data[0]["id"]
        persona['id'] = persona_id
        saved_personas.append(persona)
    persona_objects = [PersonaIn(name=p['name'], prompt=p['prompt'], id=p['id']) for p in saved_personas]
    return {"personas": persona_objects}

@router.post("/generate-prompt")
def generate_prompt(data: GeneratePromptRequest):
    topic_summary = data.topic
    def detect_language(text):
        for c in text:
            if '\u0590' <= c <= '\u05FF':
                return 'hebrew'
        return 'english'
    language = detect_language(topic_summary)
    language_display = {
        'hebrew': 'Hebrew',
        'english': 'English'
    }[language]
    age_group = f"class {data.class_id}"
    guidelines = {
        'hebrew': "הקפד שהתוכן יתאים לתלמידי בית ספר: אין לכלול קללות, אנטישמיות, גזענות או שיח שנאה מכל סוג.",
        'english': "Make sure the content is appropriate for school students: no swearing, antisemitism, racism, or any kind of hate speech."
    }[language]
    persona_prefix = {
        'hebrew': f"הנושא שלפיו תכתוב את הפוסטים והתגובות: '{topic_summary}'. קבוצת גיל: {age_group}. כתוב את כל הפוסטים והתגובות בשפה: {language_display}. {guidelines}",
        'english': f"The topic for your posts and comments: '{topic_summary}'. Age group: {age_group}. Write all posts and comments in: {language_display}. {guidelines}"
    }[language]
    return {"prompt": persona_prefix}

@router.post("/subjects")
async def create_subject(subject: SubjectIn):
    """Create a new subject."""
    try:
        # Check if subject with same name exists
        existing = supabase.table("subjects").select("id").eq("name", subject.name).maybe_single().execute()
        if existing and existing.data:
            return {"id": existing.data["id"]}
        
        # Create new subject
        insert = {
            "name": subject.name,
            "description": subject.description,
            "syllabus": subject.syllabus
        }
        resp = supabase.table("subjects").insert(insert).execute()
        if not resp.data:
            raise HTTPException(status_code=500, detail="Failed to create subject")
        return {"id": resp.data[0]["id"]}
    except Exception as e:
        print(f"Error creating subject: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 