import os
from supabase import create_client
from dotenv import load_dotenv
import pdfplumber
from docx import Document
import google.generativeai as genai

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

folder = "materials"
course_name = "history_101"

def parse_txt(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def parse_pdf(file_path):
    content = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            content += page.extract_text() + "\n"
    return content.strip()

def parse_docx(file_path):
    doc = Document(file_path)
    content = "\n".join([p.text for p in doc.paragraphs])
    return content.strip()

# Supported file types and their handlers
parser_map = {
    ".txt": parse_txt,
    ".pdf": parse_pdf,
    ".docx": parse_docx
}

# Iterate over files and insert into Supabase
for filename in os.listdir(folder):
    file_path = os.path.join(folder, filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext in parser_map:
        topic = os.path.splitext(filename)[0].replace("_", " ")
        content = parser_map[ext](file_path)

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("models/gemini-1.5-flash")

        def extract_topic_data(content):
            prompt = (
                "Analyze the following course content and extract the following:\n"
                "1. A short and clear title (2–6 words)\n"
                "2. 3–7 bullet point key ideas\n"
                "3. A short summary for internal use (1–2 sentences)\n\n"
                "Content:\n" + content[:3000] +  # Keep under token limits
                "\n\nRespond in JSON with keys: title, key_points (as a list), summary."
            )
            response = model.generate_content(prompt)
            try:
                data = eval(response.text)  # Be cautious; you can use json.loads with stricter formatting
                return data
            except Exception as e:
                print("Error parsing Gemini response:", e)
                return {
                    "title": "Untitled",
                    "key_points": [],
                    "summary": "No summary available."
                }

        topic_data = extract_topic_data(content)

        # Insert into Supabase
        supabase.table("materials").insert({
            "course": course_name,
            "topic": topic_data["title"],
            "content": content,
            "summary": topic_data["summary"],
            "key_points": "\n".join(topic_data["key_points"])
        }).execute()

        print(f"Uploaded: {filename}")
    else:
        print(f"Skipped unsupported file: {filename}")