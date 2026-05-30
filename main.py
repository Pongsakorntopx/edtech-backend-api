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

app = FastAPI(title="EdTech RPG Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# เชื่อมต่อฐานข้อมูลและ AI
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ฟังก์ชันดึงข้อความจากไฟล์ (เวอร์ชันจำลองเบื้องต้น)
async def extract_text(file: UploadFile):
    content = await file.read()
    return f"[ข้อมูลถูกดึงมาจากไฟล์: {file.filename}]"

# ฟังก์ชันสั่ง AI สำหรับแต่ละห้องเรียน (ทำงานแบบคู่ขนาน)
async def generate_lesson_for_cohort(grade: str, rooms: List[str], topic: str, indicators: str, rules: str, ref_text: str, goal: str):
    room_text = f"ห้อง {', '.join(rooms)}" if rooms else "ทุกห้อง"
    
    prompt = f"""
    คุณคือผู้เชี่ยวชาญด้านหลักสูตรและการออกข้อสอบ
    จงสร้างบทเรียนวิชาสังคมศึกษา สำหรับนักเรียนชั้น {grade} {room_text} โรงเรียนหารเทารังสีประชาสรรค์ จังหวัดพัทลุง
    
    หัวข้อ: {topic}
    ตัวชี้วัด: {indicators}
    เป้าหมายความยาก: {goal}
    ข้อมูลอ้างอิง: {ref_text}
    
    ข้อกำหนดการสอบ: {rules}
    **กฎเหล็ก**: ข้อสอบทุกข้อต้องอ้างอิงจากเนื้อหาที่คุณสร้างเท่านั้น
    
    ตอบกลับมาเป็น JSON Format ตามโครงสร้างนี้เท่านั้น: 
    {{
        "lesson_title": "...", 
        "content_blocks": [{{"heading": "...", "body": "..."}}], 
        "key_takeaways": ["..."], 
        "quizzes": [
            {{"type": "mcq", "question": "...", "options": ["ก.", "ข.", "ค.", "ง."], "correct_answer": "ก.", "explain": "..."}}
        ], 
        "target_rooms": {json.dumps(rooms)}
    }}
    """
    
    # รัน AI โดยไม่บล็อกระบบ
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=prompt
    )
    raw_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw_text)

# API Endpoint สำหรับรับคำสั่งสร้างเนื้อหา
@app.post("/api/admin/generate-batch")
async def generate_batch_lessons(
    teacher_id: str = Form(...),
    grade_level: str = Form(...),
    indicators_json: str = Form(...), 
    topic: str = Form(...),
    cohorts_json: str = Form(...), 
    quiz_config_json: str = Form(...),
    file: Optional[UploadFile] = File(None)
):
    # 1. ตรวจสอบสิทธิ์ (ต้องเป็นคุณครู)
    res = supabase.table("users").select("role").eq("user_id", teacher_id).execute()
    if not res.data or res.data[0].get("role") != "teacher":
        raise HTTPException(status_code=403, detail="ระบบนี้สำหรับคุณครูเท่านั้น")

    # 2. จัดเตรียมข้อมูล
    indicators = json.loads(indicators_json)
    cohorts = json.loads(cohorts_json)
    quiz_config = json.loads(quiz_config_json)
    
    ref_text = await extract_text(file) if file else "ใช้ความรู้ที่ถูกต้องตามหลักวิชาการ"
    ind_text = "\n".join([f"- {i}" for i in indicators])
    rules = f"- ปรนัย {quiz_config.get('mcq', 0)} ข้อ \n- อัตนัย {quiz_config.get('essay', 0)} ข้อ"

    # 3. ส่งคำสั่งประมวลผลพร้อมกันหลายห้อง
    tasks = []
    for cohort in cohorts:
        task = generate_lesson_for_cohort(
            grade=grade_level, rooms=cohort["rooms"], topic=topic, 
            indicators=ind_text, rules=rules, ref_text=ref_text, goal=cohort["goal"]
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)

    return {
        "status": "success",
        "message": f"สร้างเนื้อหาสำเร็จสำหรับ {len(results)} กลุ่มเป้าหมาย",
        "data": results
    }