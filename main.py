import os
import json
import asyncio
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from google import genai
from dotenv import load_dotenv

# โหลดค่าความลับจากไฟล์ .env
load_dotenv()

app = FastAPI(title="EdTech AI Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# เชื่อมต่อฐานข้อมูลและ AI
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

async def extract_text(file: UploadFile):
    content = await file.read()
    return f"[ข้อมูลถูกดึงมาจากไฟล์อ้างอิง: {file.filename}]"

async def generate_lesson_for_cohort(strand: str, grade: str, rooms: List[str], topic: str, indicators: str, rules: str, ref_text: str, goal: str, detail_level: str):
    
    # 💡 ปรับปรุงคำสั่งบังคับ AI: ให้แบ่งเนื้อหาเป็นหน้าๆ (Pages)
    detail_instruction = f"""
    **กฎเหล็กด้านเนื้อหาและรูปแบบ (CRITICAL):**
    1. **ห้ามระบุชื่อห้อง:** ในการเขียนทักทาย ห้ามระบุชื่อห้อง (เช่น ห้อง 1, 2) เด็ดขาด ให้ระบุแค่ระดับชั้น เช่น "สวัสดีนักเรียนชั้น {grade} ทุกคน"
    2. **ความละเอียดขั้นสุดยอด:** เนื้อหาต้องลึกซึ้ง ละเอียด และมีปริมาณมาก (2,000-3,000 คำ) ขยายความทุกประเด็นย่อย พร้อมยกตัวอย่างสถานการณ์จริงให้เข้าใจง่าย
    3. **การแบ่งหน้า (Pagination):** คุณต้องแบ่งเนื้อหาทั้งหมดออกเป็น "หน้าย่อยๆ (Pages)" อย่างน้อย 4-6 หน้า เพื่อให้นักเรียนกดปุ่มอ่าน "หน้าถัดไป" ทีละหน้าได้โดยไม่ตาลาย
    """
    
    prompt = f"""
    คุณคือผู้เชี่ยวชาญด้านหลักสูตรแกนกลางการศึกษาขั้นพื้นฐาน พ.ศ. 2551 และเป็นคุณครูระดับเชี่ยวชาญ
    จงสร้างบทเรียนวิชาสังคมศึกษา ศาสนา และวัฒนธรรม ({strand}) สำหรับนักเรียนชั้น {grade}
    
    หัวข้อการเรียนรู้: {topic}
    ตัวชี้วัด: 
    {indicators}
    
    เป้าหมายความยาก: {goal}
    ข้อมูลอ้างอิงเพิ่มเติม: {ref_text}
    
    {detail_instruction}
    
    ข้อกำหนดการสร้างแบบทดสอบ: 
    {rules}
    (ข้อสอบทุกข้อต้องอ้างอิงจากเนื้อหาที่คุณเพิ่งเขียนอธิบายไปเท่านั้น)
    
    ตอบกลับมาเป็น JSON Format ตามโครงสร้างนี้เท่านั้น ห้ามมีข้อความอื่นปน: 
    {{
        "lesson_title": "ชื่อบทเรียน", 
        "pages": [
            {{
                "page_number": 1,
                "heading": "หัวข้อของหน้านี้", 
                "body": "เนื้อหาที่อธิบายอย่างละเอียดสุดๆ (รองรับการใช้ย่อหน้าและ Bullet)..."
            }},
            {{
                "page_number": 2,
                "heading": "...", 
                "body": "..."
            }}
        ], 
        "key_takeaways": ["สรุปประเด็นสำคัญข้อ 1", "สรุปประเด็นสำคัญข้อ 2"], 
        "quizzes": [
            {{"type": "mcq", "question": "...", "options": ["ก.", "ข.", "ค.", "ง."], "correct_answer": "ก.", "explain": "คำอธิบายเฉลย..."}},
            {{"type": "tf", "question": "...", "options": ["ถูก", "ผิด"], "correct_answer": "ถูก", "explain": "..."}},
            {{"type": "short", "question": "...", "correct_answer": "...", "explain": "..."}},
            {{"type": "essay", "question": "...", "grading_criteria": "เกณฑ์การให้คะแนนอย่างละเอียด..."}}
        ], 
        "target_rooms": {json.dumps(rooms)}
    }}
    """
    
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=prompt
    )
    raw_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw_text)

@app.post("/api/admin/generate-batch")
async def generate_batch_lessons(
    teacher_id: str = Form(...),
    strand: str = Form(""),
    grade_level: str = Form(...),
    indicators_json: str = Form(...), 
    topic: str = Form(...),
    cohorts_json: str = Form(...), 
    quiz_config_json: str = Form(...),
    student_settings_json: str = Form("{}"), 
    file: Optional[UploadFile] = File(None)
):
    res = supabase.table("users").select("role").eq("user_id", teacher_id).execute()
    if not res.data or res.data[0].get("role") != "teacher":
        raise HTTPException(status_code=403, detail="ระบบนี้สำหรับคุณครูเท่านั้น")

    indicators = json.loads(indicators_json)
    cohorts = json.loads(cohorts_json)
    quiz_config = json.loads(quiz_config_json)
    student_settings = json.loads(student_settings_json)
    
    detail_level = student_settings.get("content_detail_level", "ละเอียดมาก")
    ref_text = await extract_text(file) if file else "อ้างอิงเนื้อหาจากหลักสูตรแกนกลางฯ 2551"
    ind_text = "\n".join([f"- {i}" for i in indicators])
    
    rules = f"- ปรนัย (4 ตัวเลือก) {quiz_config.get('mcq', 0)} ข้อ\n" \
            f"- ถูก/ผิด {quiz_config.get('tf', 0)} ข้อ\n" \
            f"- เติมคำสั้นๆ {quiz_config.get('short', 0)} ข้อ\n" \
            f"- อัตนัย (เขียนตอบยาว) {quiz_config.get('essay', 0)} ข้อ"

    tasks = []
    for cohort in cohorts:
        task = generate_lesson_for_cohort(
            strand=strand, grade=grade_level, rooms=cohort["rooms"], 
            topic=topic, indicators=ind_text, rules=rules, 
            ref_text=ref_text, goal=cohort["goal"], detail_level=detail_level
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)

    return {
        "status": "success",
        "message": f"สร้างเนื้อหาสำเร็จ",
        "student_settings_saved": student_settings,
        "data": results
    }
