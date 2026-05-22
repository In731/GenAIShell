# GenAIShell: GenAI-Based Terminal Assistant

[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Gemini](https://img.shields.io/badge/API-Gemini%20API-orange.svg)](https://ai.google.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**GenAIShell** is a production-quality, modular, and security-hardened terminal assistant. It utilizes Python and the **Gemini API** to translate natural language prompts into precise terminal actions, executing them securely with strict sandboxing and real-time user-in-the-loop confirmations.

---

## 🌟 Key Features

1. **Natural Language to Shell Execution**: Translate conversational intents into execution scripts (cross-platform compatible on Windows PowerShell, macOS, and Linux).
2. **Strict Command Sandboxing & Filtering**: Blocks malicious destructive actions (e.g. fork bombs, system formatting, raw disk writes) via custom security guardrails.
3. **Immersive Interactive Shell**: Rich interactive shell loop incorporating formatted Markdown panels and command feedback.
4. **Agent Loop (ReAct Plan Execution)**: Multi-step reasoning loops allowing the assistant to chain execution goals sequentially (e.g., locate file, copy file, commit to git).
5. **Local Persistent Memory**: Transactional SQLite session tracking to maintain conversational state across system restarts.
6. **Local NumPy Vector Store**: Lightweight semantic database for RAG capabilities without native compilation tool burdens.
7. **Extensible Plugin Registry**: Single-decorator mapping of Python functions to Gemini tools.

---

## 🏗️ High-Level System Architecture

```
                                  [User Input]
                                       │
                                       ▼
                             ┌───────────────────┐
                             │  Typer CLI Layer  │
                             └─────────┬─────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │ Core ReAct Agent Orchestrator │
                       └───────────────┬───────────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
        ┌──────────────┐       ┌──────────────┐       ┌───────────────┐
        │ SQLite Memory│       │ Vector RAG   │       │ Plugin system │
        └──────────────┘       └──────────────┘       └───────┬───────┘
                                                              │
                                                              ▼
                                                      ┌───────────────┐
                                                      │ Security Check│
                                                      └───────┬───────┘
                                                              │
                                                    [Safe]    ▼    [Risky]
                                                     ┌────────┴────────┐
                                                     ▼                 ▼
                                             ┌──────────────┐   ┌──────────────┐
                                             │ Executor Run │   │ User Prompt  │
                                             └──────────────┘   └──────────────┘
```

---

## 📂 Project Directory Structure

```text
terminal_assistant/
│
├── config/
│   └── settings.py          # Configuration management via Pydantic (BaseSettings)
│
├── security/
│   └── guardrails.py        # Strict command blocking, classification rules, and escapes
│
├── core/
│   ├── orchestrator.py      # LLM connection helper and vector embedding generation
│   ├── executor.py          # Secure subprocess launcher (with timeout support)
│   └── agent_loop.py        # ReAct conversational orchestrator loop
│
├── storage/
│   ├── memory.py            # Persists session history, commands, and schemas via SQLite
│   └── vector_store.py      # Local NumPy-optimized cosine similarity database
│
├── tools/
│   ├── base.py              # Single-decorator system tool registration controller
│   ├── file_tools.py        # Search, summary, and CRUD operations
│   ├── git_tools.py         # Version-control commit utilities
│   ├── system_tools.py      # Process monitors and port terminators
│   └── search_tools.py      # Local semantic RAG search
│
├── cli/
│   └── main.py              # Gorgeous interactive Typer console using Rich formatting
│
├── utils/
│   └── logging.py           # Configured system file & Console logging
│
├── requirements.txt         # Production-level python packages
├── Dockerfile               # Multi-stage containerized execution runner
├── .env.example             # Template for API credentials
├── main.py                  # Entry Point
└── README.md                # System documentation
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- **Python 3.11+** installed on the host machine.
- A **Gemini API Key** (obtainable via [Google AI Studio](https://aistudio.google.com/)).

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone <repository-url>
cd Terminal_based-project

# Initialize virtual environment
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 3. Configure API Credentials
Create a `.env` file in the root directory (based on `.env.example`):
```env
GEMINI_API_KEY=AIzaSy...your_gemini_key
SAFE_MODE_ENABLED=True
MAX_SHELL_TIMEOUT=30
LOG_LEVEL=INFO
```

---

## 🚀 Running the Assistant

### 1. Interactive Immersive Console (Recommended)
Launch the beautiful continuous interactive loop where the assistant maintains session context:
```bash
python main.py interactive
```

### 2. Single Task Mode
Execute a quick natural language task directly and terminate immediately:
```bash
python main.py ask "Create a folder named backups and list files in it"
```

### 3. Local RAG Contextual Indexing
Add text or documentation files to the local semantic index for context queries:
```bash
python main.py docs-index "/path/to/documentation.txt" --category "FastAPI"
```

### 4. Clear Local Indexes
Flush both the SQLite session files and vector store index schemas:
```bash
python main.py clear-history
```

---

## 🛡️ Security Implementation (Defense in Depth)

Security is paramount when allowing an LLM to interact with local terminal subprocesses:

- **Regex Command Guardrails**: Checks incoming shell calls against critical system destruction patterns (`rm -rf /`, `Format-Volume`, fork bombs, raw dd block copying). Blocked items are instantly halted with security error alerts.
- **Classification Engine**: Sorts operations into:
  - **Blocked**: Permanently intercepted.
  - **Risky**: Commands containing staging write redirection (`>`), user escalations (`sudo`, `runas`), process terminators (`kill`, `Stop-Process`), or file deletions.
  - **Safe**: Safe reads or listings.
- **User-in-the-Loop Interception**: Risky actions block the execution pipeline, popping up a gorgeous yellow alert panel showing the target action and reasoning, prompting the user for an interactive `[Y/N]` approval check.
- **Subprocess Runaway Timeouts**: Enforces execution timeouts (defaults to `30s`) inside the core asynchronous executor. If exceeded, the subshell process and all of its spawned child trees are terminated cleanly (using process group kills on Windows/Linux) to prevent runaway resource leaks.

---

## 🐳 Running Under Docker (Sandboxed Environment)

To ensure the terminal assistant has absolutely zero risk of modifying your host machine, you can run it inside a fully isolated Docker container:

```bash
# 1. Build sandboxed Docker container
docker build -t genai-shell .

# 2. Run container in interactive mode mounting local data persistent folder
docker run -it -e GEMINI_API_KEY="AIzaSy..." -v "$(pwd)/data:/app/data" genai-shell interactive

