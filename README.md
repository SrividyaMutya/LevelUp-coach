# LevelUp-coach

A GenAI-powered coach that generates practice questions on a topic (or for a
job role), evaluates your written answers, gives structured feedback, and
adapts difficulty as you go. Built for InnovaHack Chapter 1 — Problem
Statement 2 (Gen AI domain).

## Stack

- **Frontend:** React 18 (via CDN, no JSX, no build step) + plain CSS
- **Backend:** FastAPI (Python)
- **Database:** SQLite (persists sessions, questions, answers)
- **Model:** Google Gemini (free tier, no credit card) for question generation and answer evaluation

## How it meets the brief

| Focus area                        | How it's implemented                                                                 |
|-----------------------------------|----------------------------------------------------------------------------------------|
| Dynamic question generation       | `/api/session/{id}/question` — prompts Claude for a new question on the given topic/role at the current difficulty, avoiding repeats. |
| Answer evaluation                 | `/api/answer` — sends the question + answer to Claude, gets back score, strengths, gaps, resource. |
| Structured, actionable feedback   | Response schema is strict JSON: score, strengths, gaps, suggested_resource.            |
| Adaptive difficulty               | **Rule-based**, not just "whatever the LLM says": 2 strong answers (score ≥7) in a row levels up, 2 weak answers (score ≤3) in a row levels down. Auditable and explainable to judges. |
| Persistence                       | SQLite stores every session, question, and answer — `/api/session/{id}/summary` returns a full session report. |

## Run it

### 0. Get a free Gemini API key (no credit card)

Go to https://aistudio.google.com/apikey, sign in with any Google account,
click "Create API key". Takes under a minute.

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
export GEMINI_API_KEY=AIza...      # Windows: set GEMINI_API_KEY=AIza...
uvicorn main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. SQLite file `coach.db` is created
automatically in the `backend/` folder on first run.

### 2. Frontend

No build step needed — it's plain JS + React via CDN.

```bash
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500` in your browser.

> If your backend runs on a different host/port, update `API_BASE` at the
> top of `frontend/app.js`.

## API summary

- `POST /api/session` `{subject, mode}` → `{session_id, difficulty}`
- `POST /api/session/{id}/question` → `{question_id, question, difficulty}`
- `POST /api/answer` `{session_id, question_id, answer}` → `{score, strengths, gaps, suggested_resource, next_difficulty, difficulty_changed}`
- `GET /api/session/{id}/summary` → full session report (avg score, per-question history)

## Notes for the demo video

1. Show picking "Study a topic" or "Prep for a role" and entering a subject.
2. Show a generated question, type a deliberately weak answer, submit —
   point out the low score and the difficulty dial staying put or dropping.
3. Answer a couple more strongly — show the difficulty dial move up and
   explain the 2-in-a-row rule (this is your strongest "technical
   feasibility" talking point — it's not a black box).
4. Hit `/api/session/{id}/summary` (or add a "View report" button) to show
   persistence across the session.

## Known limits / next steps if you had more time

- Voice input (Web Speech API) for spoken answers — not yet wired in.
- `suggested_resource` describes a *type* of resource rather than a
  specific named source, to avoid the model hallucinating a book/course
  that doesn't exist.
- Single-user, no auth — fine for a hackathon demo, not for production.
