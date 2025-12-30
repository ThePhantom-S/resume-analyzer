import os
import json
from dotenv import load_dotenv
from google import genai
from pathlib import Path
from typing import Optional, Dict

# Load .env once
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Using the requested model
MODEL = "gemini-2.5-flash" 

_client = None 

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not found in environment")
        _client = genai.Client(api_key=api_key)
    return _client

def analyze_resume(resume_text: str, target_role: str, known_skills: Optional[str] = "") -> Dict:
    client = get_client()

    # Refined prompt to include "Eligible Roles" logic
    prompt = f"""
        You are an elite Career Strategy Engine with deep expertise in global tech markets and recruitment algorithms. 
        Analyze the inputs provided to generate a high-fidelity, actionable job readiness report.

        INPUT DATA:
        - TARGET ROLE: {target_role}
        - RESUME CONTENT: {resume_text}
        - ADDITIONAL CONTEXT/SKILLS: {known_skills}

        ANALYTICAL TASKS:
        1. READINESS SCORE: Calculate a percentage (0-100) based on how the Resume + Known Skills align with current industry expectations for the TARGET ROLE.
        2. SKILL QUANTIZATION:
        - 'skills': Verified assets found in the input.
        - 'required_skills': The industry-standard stack for the target role in 2025.
        - 'missing_skills': The critical gap the user must bridge.
        3. MARKET PIVOTS: Identify 3-5 'eligible_roles' where the user's current skill overlap is >80%.
        4. COMPENSATION BENCHMARKING: Provide estimated annual salary tiers in INR (India Market) formatted with commas (e.g., "12,00,000").
        5. MULTI-TRACK MASTERY ROADMAP: Generate exhaustive day-by-day upskilling plans for 30, 60, and 90-day durations.

        ROADMAP CONTENT STANDARDS:
        - 'day': Format as "Day X".
        - 'video': Provide a direct YouTube search link: https://www.youtube.com/results?search_query=[topic]+tutorial.
        - 'practice': Provide a specific LeetCode problem URL, a GitHub repo template, or a highly specific project idea.
        - 'docs': Provide the absolute URL to the official technical documentation (e.g., docs.python.org, react.dev).

        STRICT OUTPUT RULE: Return valid JSON ONLY. No conversational filler.

        RESPONSE SCHEMA:
        {{
        "readiness_score": 0,
        "skills": ["string"],
        "required_skills": ["string"],
        "missing_skills": ["string"],
        "eligible_roles": ["string"],
        "salary_tiers": {{
            "entry": "string",
            "mid": "string",
            "senior": "string"
        }},
        "preparation_plans": {{
            "30": [{{ "day": "string", "topic": "string", "description": "string", "video": "string", "practice": "string", "docs": "string" }}],
            "60": [{{ "day": "string", "topic": "string", "description": "string", "video": "string", "practice": "string", "docs": "string" }}],
            "90": [{{ "day": "string", "topic": "string", "description": "string", "video": "string", "practice": "string", "docs": "string" }}]
        }}
        }}
    """

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        )
        
        return json.loads(response.text)

    except Exception as e:
        return {
            "error": "AI Analysis Failed",
            "details": str(e)
        }