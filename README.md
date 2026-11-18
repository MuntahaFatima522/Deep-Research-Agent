# Deep Research Agent:

An autonomous research agent built with Python 3.11, LangGraph, LangChain, and FastAPI. It decomposes complex questions into targeted sub-questions, executes parallel web searches and document extractions via Tavily, organizes evidence, conducts gap analysis, writes grounded reports, verifies factual claims against source snippets, and streams live execution events via Server-Sent Events (SSE).

Architecture & Workflow
text
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


## What You Need

- A Linux desktop with internet access
- The project ZIP from GitHub
- A Gemini API key and a Tavily API key (Step 2)

---

## Step 1: Download the Project

1. Open your browser and go to your GitHub repository.
2. Click the green **Code** button, then **Download ZIP**.
3. Open the **Files** app and go to **Downloads**.
4. Right-click `deep-research-agent-main.zip` and choose **Extract Here**.

A folder named `deep-research-agent-main` appears. You may move it to **Documents** if you like.

---

## Step 2: Get Your Two API Keys

An API key is a secret password which tells a service that a request comes from you.

**Gemini key**

1. Open `aistudio.google.com/api-keys` and sign in with your Google account.
2. Click **Create API key**.
3. Copy the key and paste it into a temporary text file for now.

**Tavily key**

1. Open `app.tavily.com` and sign up.
2. Find **API Keys** in the dashboard and copy your key.
3. Paste it into the same temporary text file.

Never share these keys, post them, or put them in screenshots.

---

## Step 3: Install VS Code

1. Open **Ubuntu Software** (or **App Center**).
2. Search for **Visual Studio Code** and click **Install**.
3. Enter your password when asked.

If it does not appear in your app store, download the `.deb` file from `code.visualstudio.com`, then double-click it in the **Files** app and click **Install**.

---

## Step 4: Open the Project in VS Code

1. Start **VS Code** from the applications menu.
2. Click **File**, then **Open Folder**.
3. Choose `deep-research-agent-main` and click **OK**.
4. Click **Yes, I trust the authors** when asked.
5. Click the **Extensions** icon (four squares) on the left, search for **Python**, and install the one from Microsoft.

---

## Step 5: Create the Virtual Environment and Install Libraries

A virtual environment is a separate toolbox for this project, so its libraries never clash with other software.

1. Press `Ctrl + Shift + P` to open the Command Palette.
2. Type **Python: Create Environment** and press Enter.
3. Choose **Venv**.
4. Choose a Python interpreter. It must be version **3.11 or higher**; the version shows next to each option.
5. Tick the box beside `backend/requirements.txt` when VS Code lists dependency files, then click **OK**.
6. Wait until the progress message in the bottom right finishes. This takes a few minutes.

If VS Code says the environment could not be created, the system is missing one package. Open **Terminal**, then **New Terminal** from the top menu, and run this once:

```bash
sudo apt install -y python3-venv
```

Then repeat steps 1 to 6.

If `backend/requirements.txt` is not listed in step 5, finish creating the environment, open a new terminal (**Terminal**, then **New Terminal**) and run:

```bash
pip install -r backend/requirements.txt
```

**Check:** The bottom right of VS Code should show your Python version with `.venv` beside it. The terminal prompt should start with `(.venv)`.

---

## Step 6: Create the .env File and Add Your Keys

1. In the VS Code **Explorer** (left side), open the `backend` folder.
2. Right-click `.env.example` and choose **Copy**.
3. Right-click the `backend` folder and choose **Paste**.
4. Right-click the pasted file (usually named `.env copy.example`), choose **Rename**, and type `.env`. Press Enter.
5. Double-click `.env` to open it.
6. Replace the placeholder values with your keys, like this:

```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.8-flash
GOOGLE_API_KEY=paste_your_gemini_key_here
TAVILY_API_KEY=paste_your_tavily_key_here
```

7. Press `Ctrl + S` to save.

**Rules for the .env file:**

- Put no space around `=`. Correct: `GOOGLE_API_KEY=abc123`.
- Do not wrap keys in quotes.
- The file must be named exactly `.env` and sit inside the `backend` folder.
- Never upload `.env` to GitHub.

---

## Step 7: Check the Setup

1. In the top menu, click **Terminal**, then **New Terminal**.
2. Confirm the prompt starts with `(.venv)`.
3. Run:

```bash
python scripts/check_setup.py
```

The script asks the model to say hello and runs one live search. If both calls succeed, your setup works.

---

## Step 8: Run the Agent

In the same terminal, run:

```bash
python scripts/run_agent.py "Compare PostgreSQL and MongoDB for an online store"
```

You see the stages appear line by line: plan, workers, evidence, gap review, writing, verifying, and the final report. A run takes about one to two minutes.

---

## Step 9: Run the Web Server and Test It in the Browser

1. In the terminal, run:

```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

2. Open your browser and go to `http://localhost:8000/docs`.
3. Click **POST /api/runs**, then **Try it out**.
4. Replace the sample text with your question, for example:

```
{"question": "What is the impact of AI on healthcare diagnostics?"}
```

5. Click **Execute**. The response contains a `run_id`.
6. Click **GET /api/runs/{run_id}**, then **Try it out**, paste your `run_id`, and click **Execute** to see the finished report.

To stop the server, click inside the terminal and press `Ctrl + C`.

---

## Step 10: Run the Frontend (Web Screen)

The web screen lives in the `frontend` folder. Open `frontend/package.json` first and check that a `dev` script exists under `scripts`. Then, with the backend server from Step 9 still running, open a second terminal (the **+** button above the terminal panel) and run:

```bash
sudo apt install -y nodejs npm
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser. If the frontend asks for the backend address, use `http://localhost:8000`.

---

## Common Problems

- **The prompt has no `(.venv)`:** Press `Ctrl + Shift + P`, choose **Python: Select Interpreter**, and pick the one marked `.venv`. Then open a new terminal.
- **`ModuleNotFoundError`:** The libraries are not installed in the active environment. Run `pip install -r backend/requirements.txt` in a terminal showing `(.venv)`.
- **Invalid API key or error 401:** A key was copied wrongly or has a space around it. Open `backend/.env` and paste it again.
- **A setting or key is reported missing:** The file is not at `backend/.env`, or its name is wrong.
- **Error 429 or rate limit:** The free tier limit is reached. Wait a few minutes and run again.
- **Port 8000 already in use:** Another server is running. Close the old terminal, or use `--port 8001`.
- **`.env` is not visible in the Files app:** Press `Ctrl + H` to show hidden files. VS Code shows it normally.

---

## Final Checklist

- [ ] Project folder extracted and open in VS Code
- [ ] Python extension installed
- [ ] `.venv` created and active
- [ ] `backend/.env` holds both keys
- [ ] `check_setup.py` succeeded
- [ ] `run_agent.py` printed a report
- [ ] `http://localhost:8000/docs` opens in the browser
