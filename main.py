"""
LevelUp-coach
FastAPI backend with SQLite persistence.

Uses Google Gemini's free tier (no credit card needed) instead of a paid
LLM API. Get a free key in ~30 seconds at https://aistudio.google.com/apikey

Run:
    pip install -r requirements.txt
    export GEMINI_API_KEY=AIza...
    uvicorn main:app --reload --port 8000
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = os.path.join(os.path.dirname(__file__), "coach.db")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# "gemini-flash-latest" is a Google-maintained alias that always points at
# their current free-tier Flash model, so this keeps working even as Google
# renames/rotates the underlying model (e.g. 2.5 Flash -> 3.5 Flash).
MODEL = "gemini-flash-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

DIFFICULTY_LEVELS = ["Foundational", "Intermediate", "Advanced", "Expert"]

app = FastAPI(title="LevelUp-coach")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon speed; restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- DB setup ----------

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                mode TEXT NOT NULL,           -- 'topic' or 'role'
                difficulty_idx INTEGER NOT NULL DEFAULT 1,
                streak INTEGER NOT NULL DEFAULT 0,   -- consecutive good/bad answers
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                answer TEXT NOT NULL,
                score INTEGER NOT NULL,
                strengths TEXT NOT NULL,
                gaps TEXT NOT NULL,
                suggested_resource TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id)
            );
            """
        )


init_db()


# ---------- Gemini API helper ----------

def call_llm(system_prompt: str, user_prompt: str) -> dict:
    if not GEMINI_API_KEY:
        raise HTTPException(
            500,
            "GEMINI_API_KEY is not set on the server. Get a free key at "
            "https://aistudio.google.com/apikey and export it before starting uvicorn.",
        )
    resp = requests.post(
        GEMINI_URL,
        params={"key": GEMINI_API_KEY},
        headers={"Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1000,
                "responseMimeType": "application/json",
            },
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"Gemini API error: {resp.text}")
    data = resp.json()
    try:
        candidates = data["candidates"]
        parts = candidates[0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError):
        raise HTTPException(502, f"Unexpected Gemini response shape: {json.dumps(data)[:300]}")
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(502, f"Model did not return valid JSON: {text[:300]}")


# ---------- Rule-based adaptive difficulty ----------
# We do NOT blindly trust the model's opinion on difficulty. We combine the
# model's score with an explicit, auditable rule so judges can see exactly
# why difficulty moved.

def next_difficulty_idx(current_idx: int, streak: int, score: int) -> (int, int):
    """
    Returns (new_idx, new_streak).
    Rule:
      - score >= 7 (good answer): increment streak. 2 good answers in a row -> level up.
      - score <= 3 (weak answer): decrement streak. 2 weak answers in a row -> level down.
      - otherwise (4-6, middling): streak resets to 0, difficulty stays put.
    """
    if score >= 7:
        streak = streak + 1 if streak >= 0 else 1
    elif score <= 3:
        streak = streak - 1 if streak <= 0 else -1
    else:
        streak = 0

    new_idx = current_idx
    if streak >= 2:
        new_idx = min(current_idx + 1, len(DIFFICULTY_LEVELS) - 1)
        streak = 0
    elif streak <= -2:
        new_idx = max(current_idx - 1, 0)
        streak = 0

    return new_idx, streak


# ---------- Schemas ----------

class CreateSessionRequest(BaseModel):
    subject: str
    mode: str  # 'topic' or 'role'


class AnswerRequest(BaseModel):
    session_id: int
    question_id: int
    answer: str


# ---------- Routes ----------

@app.post("/api/session")
def create_session(req: CreateSessionRequest):
    if req.mode not in ("topic", "role"):
        raise HTTPException(400, "mode must be 'topic' or 'role'")
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (subject, mode, difficulty_idx, streak, created_at) VALUES (?, ?, 1, 0, ?)",
            (req.subject, req.mode, time.time()),
        )
        session_id = cur.lastrowid
    return {"session_id": session_id, "difficulty": DIFFICULTY_LEVELS[1]}


@app.post("/api/session/{session_id}/question")
def generate_question(session_id: int):
    with get_db() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")
        prior = conn.execute(
            "SELECT question FROM questions WHERE session_id = ?", (session_id,)
        ).fetchall()

    difficulty = DIFFICULTY_LEVELS[session["difficulty_idx"]]
    prior_list = " | ".join(r["question"] for r in prior)

    if session["mode"] == "topic":
        user_prompt = (
            f'Generate one NEW {difficulty}-level practice question to test understanding '
            f'of the topic "{session["subject"]}". Make it specific, not generic.'
            + (f" Avoid repeating these prior questions: {prior_list}" if prior_list else "")
        )
    else:
        user_prompt = (
            f'Generate one NEW {difficulty}-level interview question for a candidate applying '
            f'to the role "{session["subject"]}". Make it specific to that role, not generic.'
            + (f" Avoid repeating these prior questions: {prior_list}" if prior_list else "")
        )

    system_prompt = (
        'You are an exam question generator. Respond with ONLY raw JSON, no markdown, no preamble. '
        'Schema: {"question": string, "difficulty": string}. '
        'difficulty must be one of: Foundational, Intermediate, Advanced, Expert.'
    )

    parsed = call_llm(system_prompt, user_prompt)

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO questions (session_id, question, difficulty, created_at) VALUES (?, ?, ?, ?)",
            (session_id, parsed["question"], parsed.get("difficulty", difficulty), time.time()),
        )
        question_id = cur.lastrowid

    return {"question_id": question_id, "question": parsed["question"], "difficulty": parsed.get("difficulty", difficulty)}


@app.post("/api/answer")
def submit_answer(req: AnswerRequest):
    with get_db() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (req.session_id,)).fetchone()
        question = conn.execute("SELECT * FROM questions WHERE id = ?", (req.question_id,)).fetchone()
        if not session or not question:
            raise HTTPException(404, "Session or question not found")

    system_prompt = (
        'You are a rigorous but encouraging examiner. Respond with ONLY raw JSON, no markdown. '
        'Schema: {"score": number (0-10 integer), "strengths": string, "gaps": string, '
        '"suggested_resource": string}. suggested_resource should describe a TYPE of resource '
        '(e.g. "a beginner tutorial on X", "official docs for Y") rather than naming a specific '
        'unverifiable book or course.'
    )
    user_prompt = (
        f'Subject: "{session["subject"]}" ({session["mode"]})\n'
        f'Question asked (difficulty: {question["difficulty"]}): "{question["question"]}"\n'
        f'Candidate\'s answer: "{req.answer}"\n\n'
        f'Evaluate the answer. Be specific about what was strong and what was missing.'
    )

    parsed = call_llm(system_prompt, user_prompt)
    score = int(parsed["score"])

    new_idx, new_streak = next_difficulty_idx(session["difficulty_idx"], session["streak"], score)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO answers
               (question_id, answer, score, strengths, gaps, suggested_resource, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (req.question_id, req.answer, score, parsed["strengths"], parsed["gaps"],
             parsed["suggested_resource"], time.time()),
        )
        conn.execute(
            "UPDATE sessions SET difficulty_idx = ?, streak = ? WHERE id = ?",
            (new_idx, new_streak, req.session_id),
        )

    return {
        "score": score,
        "strengths": parsed["strengths"],
        "gaps": parsed["gaps"],
        "suggested_resource": parsed["suggested_resource"],
        "next_difficulty": DIFFICULTY_LEVELS[new_idx],
        "difficulty_changed": new_idx != session["difficulty_idx"],
    }


@app.get("/api/session/{session_id}/summary")
def session_summary(session_id: int):
    with get_db() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")
        rows = conn.execute(
            """SELECT q.question, q.difficulty, a.answer, a.score, a.strengths, a.gaps, a.suggested_resource
               FROM answers a JOIN questions q ON a.question_id = q.id
               WHERE q.session_id = ? ORDER BY a.id ASC""",
            (session_id,),
        ).fetchall()

    history = [dict(r) for r in rows]
    avg_score = round(sum(r["score"] for r in history) / len(history), 1) if history else None

    return {
        "subject": session["subject"],
        "mode": session["mode"],
        "current_difficulty": DIFFICULTY_LEVELS[session["difficulty_idx"]],
        "questions_answered": len(history),
        "average_score": avg_score,
        "history": history,
    }


@app.get("/")
def health():
    return {"status": "ok", "service": "levelup-coach-backend"}
