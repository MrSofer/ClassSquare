import os
import google.generativeai as genai
from dotenv import load_dotenv
from docx import Document
import PyPDF2

def extract_text_from_file(filename):
    ext = filename.lower().split('.')[-1]
    if ext == 'txt':
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    elif ext == 'docx':
        doc = Document(filename)
        return '\n'.join([p.text for p in doc.paragraphs])
    elif ext == 'pdf':
        with open(filename, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            return '\n'.join(page.extract_text() for page in reader.pages if page.extract_text())
    else:
        raise ValueError("Unsupported file type: " + ext)

def get_syllabus_json_from_gemini(text, model_name="models/gemini-1.5-flash"):
    prompt = (
        "Extract a syllabus from the following text. "
        "Return the result as a JSON object with this structure:\n"
        "{\n"
        "  \"syllabus\": {\n"
        "    \"subject_curriculum\": [\n"
        "      {\n"
        "        \"section_notes\": null,\n"
        "        \"chapters_or_topics\": [\n"
        "          {\n"
        "            \"topic_notes\": null,\n"
        "            \"topic_title\": \"...\",\n"
        "            \"detailed_points\": [],\n"
        "            \"topic_time_allocation\": null,\n"
        "            \"topic_specific_materials\": null,\n"
        "            \"is_alternative_assessment_topic\": false,\n"
        "            \"exam_exclusion_details_for_topic\": null\n"
        "          }\n"
        "        ],\n"
        "        \"main_section_title\": \"...\"\n"
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n"
        "Only output valid JSON. Here is the text:\n\n"
        f"{text}\n"
    )
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    # Try to extract JSON from the response
    import json, re
    try:
        # Try to find the first {...} block in the response
        match = re.search(r'({.*})', response.text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        else:
            return json.loads(response.text)
    except Exception as e:
        print("Could not parse JSON from Gemini response.")
        print("Raw response:", response.text)
        raise e

def main():
    load_dotenv()
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    filename = input("Enter the path to your file (pdf, txt, docx): ").strip()
    text = extract_text_from_file(filename)
    print("Extracted text, sending to Gemini...")
    syllabus_json = get_syllabus_json_from_gemini(text)
    out_file = input("Enter output filename (e.g. syllabus.json): ").strip() or "syllabus.json"
    import json
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(syllabus_json, f, ensure_ascii=False, indent=2)
    print(f"Syllabus JSON saved to {out_file}")

if __name__ == "__main__":
    main()