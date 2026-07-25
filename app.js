// LevelUp-coach
// Plain JavaScript, no JSX. Uses React.createElement directly.
// Talks to the FastAPI backend at API_BASE.

const { useState, useRef, useEffect } = React;
const h = React.createElement;

const API_BASE = "http://localhost:8000";
const DIFFICULTY_LEVELS = ["Foundational", "Intermediate", "Advanced", "Expert"];

// ---------- API helpers ----------

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || "Request failed");
  }
  return res.json();
}

async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || "Request failed");
  }
  return res.json();
}

// ---------- Root component ----------

function App() {
  const [stage, setStage] = useState("setup"); // setup | loading | question | evaluating | feedback
  const [mode, setMode] = useState("topic");
  const [subject, setSubject] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [difficulty, setDifficulty] = useState("Intermediate");
  const [difficultyIdx, setDifficultyIdx] = useState(1);
  const [question, setQuestion] = useState(null);
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState([]);
  const [feedback, setFeedback] = useState(null);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (stage === "question" && inputRef.current) inputRef.current.focus();
  }, [stage]);

  async function startSession() {
    if (!subject.trim()) return;
    setError("");
    setStage("loading");
    try {
      const created = await apiPost("/api/session", { subject, mode });
      setSessionId(created.session_id);
      const q = await apiPost(`/api/session/${created.session_id}/question`, {});
      setQuestion(q);
      setDifficulty(q.difficulty);
      setAnswer("");
      setStage("question");
    } catch (e) {
      setError("Couldn't reach the backend. Is FastAPI running on :8000?");
      setStage("setup");
    }
  }

  async function submitAnswer() {
    if (!answer.trim()) return;
    setStage("evaluating");
    setError("");
    try {
      const result = await apiPost("/api/answer", {
        session_id: sessionId,
        question_id: question.question_id,
        answer,
      });
      setFeedback(result);
      setHistory((hist) => [
        ...hist,
        { question: question.question, difficulty: question.difficulty, answer, ...result },
      ]);
      const idx = DIFFICULTY_LEVELS.indexOf(result.next_difficulty);
      if (idx >= 0) setDifficultyIdx(idx);
      setStage("feedback");
    } catch (e) {
      setError("Evaluation failed. Please try submitting again.");
      setStage("question");
    }
  }

  async function nextQuestion() {
    setFeedback(null);
    setStage("loading");
    try {
      const q = await apiPost(`/api/session/${sessionId}/question`, {});
      setQuestion(q);
      setDifficulty(q.difficulty);
      setAnswer("");
      setStage("question");
    } catch (e) {
      setError("Couldn't reach the backend. Please try again.");
      setStage("feedback");
    }
  }

  const avgScore =
    history.length > 0
      ? (history.reduce((a, b) => a + b.score, 0) / history.length).toFixed(1)
      : null;

  return h(
    "div",
    { className: "app-shell" },
    h(
      "div",
      { className: "app-inner" },
      h(Header, { mode, difficultyIdx, avgScore, questionCount: history.length }),
      error && h("div", { className: "error-box" }, error),
      stage === "setup" &&
        h(SetupCard, { mode, setMode, subject, setSubject, onStart: startSession }),
      stage === "loading" && h(LoadingCard, { label: "Drafting your next question…" }),
      stage === "evaluating" && h(LoadingCard, { label: "Reviewing your answer…" }),
      (stage === "question" || stage === "evaluating") &&
        question &&
        h(QuestionCard, {
          question,
          difficulty,
          answer,
          setAnswer,
          onSubmit: submitAnswer,
          inputRef,
          disabled: stage === "evaluating",
        }),
      stage === "feedback" && feedback && h(FeedbackCard, { feedback, onNext: nextQuestion }),
      history.length > 0 && stage !== "setup" && h(SessionLog, { history })
    )
  );
}

// ---------- Header ----------

function Header(props) {
  const { mode, difficultyIdx, avgScore, questionCount } = props;
  return h(
    "div",
    { style: { marginBottom: 28 } },
    h(
      "div",
      { className: "eyebrow" },
      "LevelUp-coach"
    ),
    h(
      "div",
      { className: "header-row" },
      h("h1", null, "The Examiner's Desk"),
      h(DifficultyDial, { difficultyIdx, avgScore, questionCount })
    ),
    h("div", { className: "divider" })
  );
}

function DifficultyDial(props) {
  const { difficultyIdx, avgScore, questionCount } = props;
  const bars = DIFFICULTY_LEVELS.map((lvl, i) =>
    h("span", {
      key: lvl,
      title: lvl,
      className: "dial-bar" + (i <= difficultyIdx ? " active" : ""),
    })
  );
  const children = [
    h(
      "div",
      { key: "level" },
      h("div", { className: "dial-label" }, "LEVEL"),
      h("div", { className: "dial-bars" }, bars)
    ),
  ];
  if (avgScore) {
    children.push(
      h(
        "div",
        { key: "avg" },
        h("div", { className: "dial-label" }, "AVG SCORE"),
        h("div", { style: { marginTop: 4, color: "#EDE6D6" } }, avgScore + " / 10")
      )
    );
  }
  if (questionCount > 0) {
    children.push(
      h(
        "div",
        { key: "count" },
        h("div", { className: "dial-label" }, "ANSWERED"),
        h("div", { style: { marginTop: 4, color: "#EDE6D6" } }, String(questionCount))
      )
    );
  }
  return h("div", { className: "dial-group" }, children);
}

// ---------- Setup ----------

function SetupCard(props) {
  const { mode, setMode, subject, setSubject, onStart } = props;
  return h(
    "div",
    { className: "card" },
    h(
      "div",
      { className: "mode-toggle" },
      h(
        "button",
        {
          className: "mode-btn" + (mode === "topic" ? " active" : ""),
          onClick: () => setMode("topic"),
        },
        "Study a topic"
      ),
      h(
        "button",
        {
          className: "mode-btn" + (mode === "role" ? " active" : ""),
          onClick: () => setMode("role"),
        },
        "Prep for a role"
      )
    ),
    h(
      "label",
      { className: "field-label" },
      mode === "topic" ? "What topic do you want to master?" : "What role are you interviewing for?"
    ),
    h("input", {
      type: "text",
      value: subject,
      onChange: (e) => setSubject(e.target.value),
      onKeyDown: (e) => {
        if (e.key === "Enter") onStart();
      },
      placeholder:
        mode === "topic"
          ? "e.g. Dynamic Programming, French Revolution"
          : "e.g. Backend Engineer, Product Manager",
    }),
    h(
      "button",
      {
        className: "btn-primary full-width",
        disabled: !subject.trim(),
        onClick: onStart,
      },
      "BEGIN SESSION"
    )
  );
}

// ---------- Loading ----------

function LoadingCard(props) {
  return h("div", { className: "card loading-card" }, props.label);
}

// ---------- Question ----------

function QuestionCard(props) {
  const { question, difficulty, answer, setAnswer, onSubmit, inputRef, disabled } = props;
  return h(
    "div",
    { className: "card" },
    h("div", { className: "q-eyebrow" }, (difficulty || "").toUpperCase() + " · QUESTION"),
    h("p", { className: "q-text" }, question.question),
    h("textarea", {
      ref: inputRef,
      rows: 6,
      value: answer,
      disabled: disabled,
      placeholder: "Write your answer here…",
      onChange: (e) => setAnswer(e.target.value),
    }),
    h(
      "button",
      {
        className: "btn-primary",
        disabled: !answer.trim() || disabled,
        onClick: onSubmit,
      },
      "SUBMIT ANSWER"
    )
  );
}

// ---------- Feedback ----------

function FeedbackCard(props) {
  const { feedback, onNext } = props;
  const scoreColor = feedback.score >= 7 ? "#5B8C6E" : feedback.score >= 4 ? "#B8935A" : "#C4634A";
  return h(
    "div",
    { className: "card" },
    h(
      "div",
      { className: "score-row" },
      h(
        "div",
        {
          className: "score-circle",
          style: { borderColor: scoreColor, color: scoreColor },
        },
        String(feedback.score)
      ),
      h(
        "div",
        null,
        h("div", { className: "score-meta-label" }, "SCORE OUT OF 10"),
        h(
          "div",
          { className: "score-meta-value" },
          "Next question difficulty: " + feedback.next_difficulty
        )
      )
    ),
    h(FeedbackRow, { label: "Strengths", text: feedback.strengths, color: "#5B8C6E" }),
    h(FeedbackRow, { label: "Gaps", text: feedback.gaps, color: "#C4634A" }),
    h(FeedbackRow, {
      label: "Suggested resource",
      text: feedback.suggested_resource,
      color: "#B8935A",
    }),
    h(
      "button",
      { className: "btn-primary", onClick: onNext },
      "NEXT QUESTION →"
    )
  );
}

function FeedbackRow(props) {
  const { label, text, color } = props;
  return h(
    "div",
    { className: "feedback-row" },
    h("div", { className: "feedback-label", style: { color } }, label.toUpperCase()),
    h("p", { className: "feedback-text" }, text)
  );
}

// ---------- Session log ----------

function SessionLog(props) {
  const { history } = props;
  return h(
    "div",
    { style: { marginTop: 24 } },
    h("div", { className: "log-title" }, "SESSION LOG (" + history.length + ")"),
    history.map((item, i) =>
      h(
        "div",
        { className: "log-item", key: i },
        h("div", { className: "log-question" }, item.question),
        h(
          "div",
          { className: "log-meta" },
          item.difficulty + " · Score " + item.score + "/10"
        )
      )
    )
  );
}

// ---------- Mount ----------

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(h(App));
