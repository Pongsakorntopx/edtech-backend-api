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
    return f"[ข้อมูลถูกดึงมาจากไฟล์อ้างอิง: {file.filename}]"

# ฟังก์ชันสั่ง AI สำหรับแต่ละห้องเรียน (ทำงานแบบคู่ขนาน)
async def generate_lesson_for_cohort(strand: str, grade: str, rooms: List[str], topic: str, indicators: str, rules: str, ref_text: str, goal: str, detail_level: str):
    room_text = f"ห้อง {', '.join(rooms)}" if rooms else "ทุกห้อง"
    
    # 💡 กำหนดความลึกของเนื้อหาตามที่คุณครูเลือกจากหน้าเว็บ
    detail_instruction = ""
    if detail_level == "ละเอียดมาก":
        detail_instruction = "เขียนเนื้อหาให้ยาวและมีความละเอียดมากที่สุด (ประมาณ 1,000 - 2,000 คำ) ขยายความทุกประเด็นย่อยอย่างลึกซึ้ง พร้อมยกตัวอย่างประกอบในชีวิตประจำวันให้ชัดเจนและเข้าใจง่าย เพื่อให้นักเรียนสามารถอ่านทำความเข้าใจได้ด้วยตนเองอย่างถ่องแท้"
    elif detail_level == "สรุปย่อ":
        detail_instruction = "เขียนเนื้อหาแบบสรุปย่อ กระชับ จับใจความสำคัญ เหมาะสำหรับการทบทวนเนื้อหาอย่างรวดเร็ว"
    else:
        detail_instruction = "เขียนเนื้อหาความยาวปานกลาง ครอบคลุมประเด็นสำคัญและมีตัวอย่างประกอบให้เข้าใจง่าย"
    
    prompt = f"""
    คุณคือคุณครูและผู้เชี่ยวชาญด้านหลักสูตรการศึกษา
    จงสร้างบทเรียนวิชาสังคมศึกษา ({strand}) สำหรับนักเรียนชั้น {grade} {room_text} โรงเรียนหารเทารังสีประชาสรรค์
    
    หัวข้อ: {topic}
    ตัวชี้วัด/จุดประสงค์การเรียนรู้: 
    {indicators}
    
    เป้าหมายความยาก: {goal}
    ระดับความลึกของเนื้อหา: {detail_instruction}
    
    ข้อมูลอ้างอิง: {ref_text}
    
    ข้อกำหนดการสร้างแบบทดสอบ: 
    {rules}
    **กฎเหล็ก**: ข้อสอบทุกข้อต้องอ้างอิงจากเนื้อหาที่คุณสร้างใน response นี้เท่านั้น เพื่อให้นักเรียนหาคำตอบได้จากบทเรียน
    
    ตอบกลับมาเป็น JSON Format ตามโครงสร้างนี้เท่านั้น ห้ามมีข้อความอื่นหรือ markdown ปน: 
    {{
        "lesson_title": "ชื่อบทเรียน", 
        "content_blocks": [
            {{
                "heading": "หัวข้อย่อย", 
                "body": "เนื้อหาที่อธิบาย..."
            }}
        ], 
        "key_takeaways": ["สรุปประเด็นสำคัญข้อ 1", "สรุปประเด็นสำคัญข้อ 2"], 
        "quizzes": [
            {{"type": "mcq", "question": "คำถามปรนัย...", "options": ["ก.", "ข.", "ค.", "ง."], "correct_answer": "ก.", "explain": "คำอธิบายเฉลย..."}},
            {{"type": "tf", "question": "คำถามถูกผิด...", "options": ["ถูก", "ผิด"], "correct_answer": "ถูก", "explain": "คำอธิบายเฉลย..."}},
            {{"type": "short", "question": "คำถามเติมคำ...", "correct_answer": "คำตอบที่ถูกต้อง", "explain": "คำอธิบายเฉลย..."}},
            {{"type": "essay", "question": "คำถามอัตนัยให้แสดงความคิดเห็น...", "grading_criteria": "เกณฑ์การให้คะแนนจาก AI..."}}
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
    # ทำความสะอาด JSON ก่อนนำไปใช้
    raw_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw_text)

# API Endpoint สำหรับรับคำสั่งสร้างเนื้อหา
@app.post("/api/admin/generate-batch")
async def generate_batch_lessons(
    teacher_id: str = Form(...),
    strand: str = Form(""),
    grade_level: str = Form(...),
    indicators_json: str = Form(...), 
    topic: str = Form(...),
    cohorts_json: str = Form(...), 
    quiz_config_json: str = Form(...),
    student_settings_json: str = Form("{}"), # รับการตั้งค่าจากหน้าเว็บ
    file: Optional[UploadFile] = File(None)
):
    # 1. ตรวจสอบสิทธิ์ (ต้องเป็นคุณครู)
    res = supabase.table("users").select("role").eq("user_id", teacher_id).execute()
    if not res.data or res.data[0].get("role") != "teacher":
        raise HTTPException(status_code=403, detail="ระบบนี้สำหรับคุณครูเท่านั้น")

    # 2. จัดเตรียมข้อมูลจาก Frontend
    indicators = json.loads(indicators_json)
    cohorts = json.loads(cohorts_json)
    quiz_config = json.loads(quiz_config_json)
    student_settings = json.loads(student_settings_json)
    
    # ดึงค่าระดับความละเอียด (ถ้าไม่มีให้ค่าเริ่มต้นเป็น ปานกลาง)
    detail_level = student_settings.get("content_detail_level", "ปานกลาง")
    
    ref_text = await extract_text(file) if file else "ใช้ความรู้ที่ถูกต้องตามหลักวิชาการ"
    ind_text = "\n".join([f"- {i}" for i in indicators])
    
    # สรุปจำนวนข้อสอบแต่ละประเภทส่งให้ AI
    rules = f"- ปรนัย (กขคง) {quiz_config.get('mcq', 0)} ข้อ\n" \
            f"- ถูก/ผิด (True/False) {quiz_config.get('tf', 0)} ข้อ\n" \
            f"- เติมคำสั้นๆ (Short Answer) {quiz_config.get('short', 0)} ข้อ\n" \
            f"- อัตนัย (เขียนตอบ) {quiz_config.get('essay', 0)} ข้อ"

    # 3. ส่งคำสั่งประมวลผลพร้อมกันหลายห้อง
    tasks = []
    for cohort in cohorts:
        task = generate_lesson_for_cohort(
            strand=strand,
            grade=grade_level, 
            rooms=cohort["rooms"], 
            topic=topic, 
            indicators=ind_text, 
            rules=rules, 
            ref_text=ref_text, 
            goal=cohort["goal"],
            detail_level=detail_level
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)

    # Note: อนาคตสามารถนำ results และ student_settings บันทึกลง Supabase ได้ตรงนี้

    return {
        "status": "success",
        "message": f"สร้างเนื้อหาสำเร็จสำหรับ {len(results)} กลุ่มเป้าหมาย",
        "student_settings_saved": student_settings, # ส่งค่า settings กลับไปให้หน้าเว็บดูด้วย
        "data": results
    }
