import os
import json
import asyncio
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from google import genai
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="EdTech AI Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

async def extract_text(file: UploadFile):
    content = await file.read()
    return f"[ข้อมูลอ้างอิง: {file.filename}]"

async def generate_lesson_for_cohort(strand: str, grade: str, rooms: List[str], topic: str, indicators: str, rules: str, ref_text: str, goal: str, detail_level: str):
    
    # 💡 กฎเหล็ก: ห้ามใช้ Markdown และเน้นความละเอียดขั้นสุด
    detail_instruction = f"""
    **กฎเหล็กด้านเนื้อหาและรูปแบบ (CRITICAL - บังคับใช้อย่างเคร่งครัด):**
    1. **ห้ามใช้เครื่องหมายอักขระพิเศษเด็ดขาด:** ห้ามพิมพ์เครื่องหมายดอกจัน (*) สำหรับตัวหนาหรือตัวเอียง ห้ามใช้เครื่องหมาย (#) หรืออักษรแปลกๆ ให้พิมพ์เป็น "ข้อความธรรมดา (Plain Text)" ที่จัดย่อหน้าเว้นวรรคอย่างถูกต้องเท่านั้น
    2. **ห้ามระบุชื่อห้อง:** ในการทักทาย ห้ามมีคำว่า ห้อง 1, ห้อง 2 ให้ระบุแค่ระดับชั้น เช่น "สวัสดีนักเรียนชั้น {grade} ทุกคน"
    3. **ความละเอียดขั้นสุดยอด (Super Detailed):** สร้างเนื้อหาให้ยาวและลึกซึ้งที่สุด (ความยาว 2,000-3,000 คำขึ้นไป) ขยายความทุกประเด็นย่อย พร้อมยกตัวอย่างสถานการณ์จริง อธิบายเหตุและผลอย่างละเอียดถี่ถ้วน
    4. **การแบ่งหน้า (Pagination):** คุณต้องแบ่งเนื้อหาที่ยาวมากๆ นี้ออกเป็นหน้าย่อยๆ (Pages) อย่างน้อย 5-8 หน้า เพื่อให้นักเรียนอ่านทีละหน้าได้ง่าย
    """
    
    prompt = f"""
    คุณคือผู้เชี่ยวชาญด้านหลักสูตรแกนกลางการศึกษาขั้นพื้นฐาน พ.ศ. 2551 และครูชำนาญการพิเศษ
    จงสร้างบทเรียนวิชาสังคมศึกษา ({strand}) สำหรับนักเรียนชั้น {grade}
    
    หัวข้อ: {topic}
    ตัวชี้วัด/จุดประสงค์: {indicators}
    ข้อมูลอ้างอิง: {ref_text}
    
    {detail_instruction}
    
    ข้อกำหนดการสร้างแบบทดสอบ (ต้องอ้างอิงจากเนื้อหาที่คุณสร้างเท่านั้น): 
    {rules}
    
    ตอบกลับมาเป็น JSON Format ตามโครงสร้างนี้เท่านั้น ห้ามมีข้อความอื่นปน: 
    {{
        "lesson_title": "ชื่อบทเรียน", 
        "pages": [
            {{
                "page_number": 1,
                "heading": "หัวข้อของหน้านี้ (ห้ามใช้ *)", 
                "body": "เนื้อหาที่อธิบายอย่างละเอียดสุดๆ (ห้ามใช้ * หรือ #)..."
            }},
            {{
                "page_number": 2,
                "heading": "...", 
                "body": "..."
            }}
        ], 
        "key_takeaways": ["สรุปประเด็น 1", "สรุปประเด็น 2"], 
        "quizzes": [
            {{"type": "mcq", "question": "...", "options": ["ก.", "ข.", "ค.", "ง."], "correct_answer": "ก.", "explain": "..."}},
            {{"type": "tf", "question": "...", "options": ["ถูก", "ผิด"], "correct_answer": "ถูก", "explain": "..."}},
            {{"type": "short", "question": "...", "correct_answer": "...", "explain": "..."}},
            {{"type": "essay", "question": "...", "grading_criteria": "..."}}
        ]
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
    
    rules = f"- ปรนัย {quiz_config.get('mcq', 0)} ข้อ\n- ถูก/ผิด {quiz_config.get('tf', 0)} ข้อ\n- เติมคำ {quiz_config.get('short', 0)} ข้อ\n- อัตนัย {quiz_config.get('essay', 0)} ข้อ"

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
