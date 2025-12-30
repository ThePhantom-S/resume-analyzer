import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# Internal project imports
from backend.gemini_engine import analyze_resume, get_client, MODEL
from backend.firebase_auth import verify_firebase_token
from supabase import acreate_client, AsyncClient

from pydantic import BaseModel
from typing import List, Optional

# --- SETUP & LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CareerGPT")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

class State:
    supabase: Optional[AsyncClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    if SUPABASE_URL and SUPABASE_KEY:
        State.supabase = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Async Supabase client initialized.")
    yield
    if State.supabase:
        await State.supabase.auth.sign_out()

app = FastAPI(title="CareerGPT API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)

# --- MODELS ---
class AnalyzeRequest(BaseModel):
    resume_text: str = Field(..., min_length=50)
    target_role: str = Field(...)
    known_skills: Optional[str] = ""

class ProgressUpdate(BaseModel):
    analysis_id: str
    day_label: str
    is_completed: bool
    duration_type: str = "30"
    skill_score: int = Field(5, ge=0, le=5)

class ExplainRequest(BaseModel):
    topic: str
    description: str

# --- ENDPOINTS ---

@app.post("/analyze")
async def analyze(req: AnalyzeRequest, user=Depends(verify_firebase_token)):
    """Generates career analysis and seeds all roadmap durations."""
    try:
        # 1. AI Analysis Call
        analysis_result = analyze_resume(req.resume_text, req.target_role, req.known_skills)
        
        # Handle AI Rate Limits (503 handling matched with Dashboard logic)
        if "error" in analysis_result:
            status = 429 if "429" in str(analysis_result["error"]) else 503
            raise HTTPException(status_code=status, detail=analysis_result["details"])

        user_id = user.get("uid")
        
        if State.supabase:
            # 2. Insert mission into 'analyses' table
            db_res = await State.supabase.table("analyses").insert({
                "user_id": str(user_id),
                "target_role": str(req.target_role),
                "eligible_roles": analysis_result.get("eligible_roles", []), 
                "readiness_score": int(analysis_result.get("readiness_score", 0)),
                "skills": analysis_result.get("skills", []), 
                "required_skills": analysis_result.get("required_skills", []), 
                "missing_skills": analysis_result.get("missing_skills", []), 
                "salary_tiers": analysis_result.get("salary_tiers", {}), 
                "preparation_plans": analysis_result.get("preparation_plans", {}) 
            }).execute()
            
            if not db_res.data:
                raise HTTPException(status_code=500, detail="Database Sync Failed.")

            analysis_id = db_res.data[0]["id"]
            analysis_result["id"] = analysis_id

            # 3. Optimized Seeding: Seed ALL plans (30, 60, 90) for the Roadmap grid
            plans = analysis_result.get("preparation_plans", {})
            progress_rows = []

            for duration, tasks in plans.items():
                for task in tasks:
                    progress_rows.append({
                        "analysis_id": str(analysis_id),
                        "user_id": str(user_id),
                        "day_label": str(task.get("day")),
                        "duration_type": str(duration),
                        "is_completed": False,
                        "skill_score": 5 
                    })
            
            if progress_rows:
                await State.supabase.table("roadmap_progress").upsert(
                    progress_rows, 
                    on_conflict="user_id,analysis_id,day_label,duration_type"
                ).execute()

        return analysis_result
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Neural Backend Crash: {e}")
        raise HTTPException(status_code=500, detail="Internal processing error.")

@app.post("/update-progress")
async def update_progress(data: ProgressUpdate, user=Depends(verify_firebase_token)):
    """Synchronizes user progress with the cloud vault"""
    if not State.supabase: 
        raise HTTPException(status_code=500, detail="Supabase offline")
    
    try:
        user_id = user.get("uid")
        res = await State.supabase.table("roadmap_progress").upsert({
            "user_id": str(user_id),
            "analysis_id": str(data.analysis_id),
            "day_label": str(data.day_label),
            "duration_type": str(data.duration_type),
            "is_completed": bool(data.is_completed),
            "skill_score": int(data.skill_score),
            "updated_at": "now()"
        }, on_conflict="user_id,analysis_id,day_label,duration_type").execute()
        
        return {"status": "success", "data": res.data}
    except Exception as e:
        logger.error(f"Progress Sync Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database conflict detected.")

@app.get("/get-progress/{analysis_id}")
async def get_progress(analysis_id: str, user=Depends(verify_firebase_token)):
    """Retrieves progress data for the Competency Radar"""
    if not State.supabase: return []
    user_id = user.get("uid")
    res = await State.supabase.table(   "roadmap_progress").select("*")\
        .eq("analysis_id", analysis_id).eq("user_id", user_id).execute()
    return res.data

@app.get("/learning-records")
async def get_records(user=Depends(verify_firebase_token)):
    """Fetches mission history for the Sidebar Vault"""
    if not State.supabase: return []
    user_id = user.get("uid")
    res = await State.supabase.table("analyses").select("*")\
        .eq("user_id", user_id).order("created_at", desc=True).execute()
    return res.data

@app.delete("/delete-record/{record_id}")
async def delete_record(record_id: str, user=Depends(verify_firebase_token)):
    """Erase specific mission data from the vault"""
    user_id = user.get("uid")
    await State.supabase.table("analyses").delete().eq("id", record_id).eq("user_id", user_id).execute()
    return {"status": "success"}

@app.post("/explain-task")
async def explain_task(req: ExplainRequest, user=Depends(verify_firebase_token)):
    """AI Mentor: Provides technical deep dives"""
    try:
        client = get_client() 
        prompt = (
            f"You are a Senior Technical Mentor. Explain the topic '{req.topic}' "
            f"clearly for a student. Context: {req.description}. "
            "Use bullet points, keep it under 150 words, and focus on practical application."
        )
        # Uses the global MODEL defined in your engine
        response = client.models.generate_content(model=MODEL, contents=prompt)
        return {"explanation": response.text}
    except Exception as e:
        logger.error(f"AI Mentor Error: {e}")
        return {"explanation": "Neural Link offline. The AI Mentor is currently recalibrating."}
class InterviewRequest(BaseModel):
    target_role: str
    last_answer: str = ""
    history: list = []

@app.post("/mock-interview")
async def mock_interview(req: InterviewRequest, user=Depends(verify_firebase_token)):
    """Simulates a technical interview session."""
    try:
        client = get_client()
        
        system_instruction = (
            f"You are a Senior Technical Interviewer for the role of {req.target_role}. "
            "Your goal is to assess the candidate's depth of knowledge. "
            "1. Ask only ONE technical question at a time. "
            "2. If the user provides an answer, give a brief 1-sentence feedback and then ask a follow-up or new question. "
            "3. Keep the conversation professional and challenging. "
            "4. If the user says 'start', ask the first introductory technical question."
        )

        # Build the conversation history
        messages = [{"role": "user", "parts": [system_instruction]}]
        for entry in req.history:
            messages.append({"role": "user", "parts": [entry['q']]})
            messages.append({"role": "model", "parts": [entry['a']]})
        
        input_text = req.last_answer if req.last_answer else "Let's start the interview."
        
        response = client.models.generate_content(
            model=MODEL,
            contents=input_text,
            config={'system_instruction': system_instruction}
        )
        
        return {"question": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
class InterviewMessage(BaseModel):
    role: str # "user" or "model"
    content: str

class InterviewRequest(BaseModel):
    target_role: str
    last_answer: str
    history: List[dict] # List of {q: str, a: str}

@app.post("/mock-interview")
async def mock_interview(req: InterviewRequest, user=Depends(verify_firebase_token)):
    """Engine for the Technical Simulation."""
    try:
        client = get_client()
        
        # Define the AI Persona
        persona = (
            f"You are a Senior Technical Lead at a top-tier tech company. "
            f"You are conducting a technical interview for the role of {req.target_role}. "
            "STRICT RULES: "
            "1. Ask exactly ONE technical question at a time. "
            "2. Evaluate the user's previous answer briefly (2 sentences max). "
            "3. Progress from fundamental concepts to complex architecture. "
            "4. If the user's answer is weak, ask a clarifying follow-up. "
            "5. Maintain a professional, slightly intimidating but fair tone."
        )

        # Reconstruct the conversation context for Gemini
        chat_context = f"Target Role: {req.target_role}\n"
        for entry in req.history:
            chat_context += f"Interviewer: {entry['q']}\nCandidate: {entry['a']}\n"
        
        chat_context += f"Candidate's latest response: {req.last_answer}"

        response = client.models.generate_content(
            model=MODEL,
            contents=chat_context,
            config={'system_instruction': persona}
        )

        return {"question": response.text}
    except Exception as e:
        logger.error(f"Interview Error: {e}")
        raise HTTPException(status_code=500, detail="Neural link failed.")