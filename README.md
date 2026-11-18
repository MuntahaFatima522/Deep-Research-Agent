# Deep Research Agent

An autonomous research agent built with **Python 3.11**, **LangGraph**, **LangChain**, and **FastAPI**. It decomposes complex questions into targeted sub-questions, executes parallel web searches and document extractions via Tavily, organizes evidence, conducts gap analysis, writes grounded reports, verifies factual claims against source snippets, and streams live execution events via Server-Sent Events (SSE).

---

## Architecture & Workflow

```text
User Question
     │
     ▼
[Plan Node] (Decomposes into 3-5 sub-questions)
     │
     ▼
[Fan-Out Workers] ──── (Parallel Workers search & read web pages)
     │
     ▼
[Merge Evidence Node] (Dedupes facts, numbers sources 1..N)
     │
     ▼
[Gaps Node] (Evaluates sufficiency; max 2 extra rounds)
     │
   ┌─┴──────────────────────────┐
   ▼ (if incomplete & < limits)  ▼ (if sufficient or reached limits)
[Fan-Out Workers]          [Synthesizer Node] (Drafts report from numbered notes)
                                │
                                ▼
                           [Verifier Node] (Fact-checks claims against snippets)
                                │
                                ▼
                           [Final Report & Stream Done]
```

---

## 1. Setup & Installation (Linux / macOS)

### Prerequisites
- Linux (Ubuntu/Debian shown below) or macOS
- Python 3.11+, `python3-venv`, and `unzip`
- Tavily API key ([tavily.com](https://tavily.com))
- Google Gemini API key or Anthropic Claude API key

On Ubuntu/Debian, install the system packages first:

```bash
sudo apt update
sudo apt install -y unzip python3 python3-venv python3-pip
python3 --version   # must print 3.11 or higher
```

### Local Setup

```bash
# 1. Download the repository as a ZIP, unzip it, and enter the folder
#    (browser: GitHub repo > green Code button > Download ZIP)
unzip deep-research-agent-main.zip
cd deep-research-agent-main

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install backend dependencies
pip install -r backend/requirements.txt

# 4. Configure environment variables
cp backend/.env.example backend/.env
# Edit backend/.env and populate your GOOGLE_API_KEY and TAVILY_API_KEY
nano backend/.env
```

Keep the virtual environment active for every command below. When you open a new terminal, run `source .venv/bin/activate` from the project folder again.

The ZIP does not contain your `.env` file, so step 4 creates it from `.env.example`.

---

## 2. Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | Model provider: `gemini` (dev) or `anthropic` (prod) | `gemini` |
| `LLM_MODEL` | Specific LLM model identifier | `gemini-3.8-flash` |
| `GOOGLE_API_KEY` | Google Gemini API key | required for Gemini |
| `ANTHROPIC_API_KEY`| Anthropic Claude API key | required for Claude |
| `TAVILY_API_KEY` | Tavily Search & Extract API key | required |
| `MAX_SEARCHES` | Maximum global search queries permitted per run | `12` |
| `MAX_ROUNDS` | Maximum iterative gap research rounds | `2` |
| `MAX_SEARCHES_PER_WORKER` | Maximum searches one worker may run | `4` |
| `RUN_TIMEOUT_SECONDS` | Hard time limit for one run | `300` |
| `LANGSMITH_TRACING` | Set to `true` to record traces (optional) | `false` |
| `LANGSMITH_API_KEY` | LangSmith API key (optional) | *(empty)* |
| `APP_ENV` | Application environment (`dev` or `prod`) | `dev` |
| `DATABASE_URL` | PostgreSQL connection string (empty = SQLite) | *(empty)* |
| `FRONTEND_URL` | Allowed CORS origin for frontend | `http://localhost:3000` |

---

## 3. How to Run

### Option A: Run CLI Agent with Live Streaming
Run deep research directly in your terminal:
```bash
python scripts/run_agent.py "Compare PostgreSQL and MongoDB for an e-commerce application managing customers, products, orders, payments, and inventory"
```

To resume an interrupted run from its saved checkpoint:
```bash
python scripts/run_agent.py --resume <run_id>
```

### Option B: Run FastAPI Server
Start the API server with live SSE streaming support:
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger API documentation will be available at: `http://localhost:8000/docs`.

---

## 4. API Endpoints & `curl` Examples

### 1. Health Check
```bash
curl -X GET http://localhost:8000/health
```
Response:
```json
{"status": "ok"}
```

### 2. Start a New Research Run
```bash
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the impact of artificial intelligence on healthcare diagnostics?"}'
```
Response:
```json
{"run_id": "run_9a8b7c6d5e"}
```

### 3. Stream Live Progress (Server-Sent Events)
```bash
curl -N -X GET http://localhost:8000/api/runs/run_9a8b7c6d5e/events
```
Sample event stream:
```text
event: message
data: {"type": "plan", "message": "Created research plan with 3 sub-questions."}

event: message
data: {"type": "worker_started", "message": "Worker started for: 'AI imaging tools'"}

event: message
data: {"type": "done", "message": "Research run completed successfully."}
```

### 4. Fetch Completed Report and Verdicts
```bash
curl -X GET http://localhost:8000/api/runs/run_9a8b7c6d5e
```

### 5. Resume an Existing Run
```bash
curl -X POST http://localhost:8000/api/runs/run_9a8b7c6d5e/resume
```

---

## 5. Switching Model Provider (Gemini to Claude)

To switch from Google Gemini (development) to Anthropic Claude (production):

1. **Update `backend/.env`**:
   ```env
   LLM_PROVIDER=anthropic
   LLM_MODEL=claude-sonnet-5-5
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```
2. **Update Cost Rates in `backend/app/cost.py`**:
   Verify input/output rates in the `PRICES` dictionary for your chosen Claude model.
3. No code changes are required: `get_llm()` in `backend/app/llm.py` automatically initializes `ChatAnthropic`.

---

## 6. Running Tests & Benchmarks

```bash
# Run all unit and workflow tests
python -m pytest backend/tests/ -v

# Run 3-question evaluation benchmark
python scripts/evaluate.py
```

---

## 7. Docker Deployment

Install Docker first (Ubuntu: `sudo apt install -y docker.io`), then build and run:
```bash
sudo docker build -t deep-research-agent .
sudo docker run -p 8000:8000 --env-file backend/.env deep-research-agent
```

---

## 8. Final Verification Checklist

- [x] **Setup & Provider**: `get_llm()` switches between Gemini and Claude dynamically via `LLM_PROVIDER`.
- [x] **Pydantic Schemas & State**: `ResearchPlan`, `Note`, `SourceDoc`, `GapCheck`, `Claim`, `ReportDraft`, and `ClaimVerdict`.
- [x] **Resilient Web Tools**: `search_web` and `read_pages` catch exceptions, log warnings, and never crash.
- [x] **Parallel Workers**: Supervisor-worker fan-out via LangGraph `Send` primitives.
- [x] **Evidence Organization**: Automatic deduplication and source numbering (1..N) without LLM overhead.
- [x] **Grounded Report Synthesis**: Generates report sections referencing note citation numbers.
- [x] **Claim Verification**: Concurrent verification of all report assertions against cited source snippets.
- [x] **Checkpointing & Persistence**: Automatic local SQLite checkpointer at `backend/data/checkpoints.sqlite` with Postgres fallback.
- [x] **FastAPI & SSE**: Live streaming API with rate limiting and CORS configuration.