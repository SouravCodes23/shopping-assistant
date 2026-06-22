# 🛍️ Shopping Assistant — AI-Powered Retail Agent

> A production-hardened AI shopping assistant built with **Google Agent Development Kit (ADK)** and **Gemini**, featuring STRIDE threat modeling, Pydantic input validation, rate limiting, and a full security test suite.

---

## 🌐 Live Demo

> 🚀 **[Live Demo on Render](https://shopping-assistant-lr3n.onrender.com)**

---

## 📖 What is This Project?

The **Shopping Assistant** is an intelligent conversational AI agent designed for a retail store. Customers can interact with it in natural language to browse products, check order status, redeem discount codes, and earn loyalty points.

Beyond being a working AI agent, this project is a **security-focused learning lab**. It demonstrates how to apply the **STRIDE threat model** to LLM-powered tool-calling agents — protecting them from real-world exploits like brute-force attacks, race conditions, input injection, and information disclosure.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🛒 **Product Catalog** | Browse products filtered by category (electronics, clothing, home) |
| 📦 **Order Status** | Check real-time shipping and delivery status for any order |
| 🎟️ **Discount Codes** | Redeem single-use promo codes (e.g. `WELCOME50`, `SUMMER20`) |
| 🌟 **Loyalty Points** | Earn 1 point per $1 USD spent — awarded per confirmed order |
| 🛡️ **Security Guardrails** | Rate limiting, Pydantic validation, atomic locks, and audit logging |
| 🤖 **Topic Guardrail** | Agent strictly answers only store-related questions |

---

## 🏗️ Project Architecture

```
shopping-assistant/
├── app/
│   ├── agent.py                    # Core agent: tools, schemas, security logic
│   ├── agent_runtime_app.py        # Vertex AI Agent Engine deployment wrapper
│   └── app_utils/                  # Telemetry and type utilities
├── tests/
│   ├── test_agent.py               # 33 outcome-based security tests
│   ├── unit/
│   │   ├── test_award_loyalty_points.py   # Unit tests for loyalty tool
│   │   └── test_dummy.py
│   ├── integration/                # Integration and runtime tests
│   └── eval/                       # Evaluation datasets and config
├── .agents/
│   ├── CONTEXT.md                  # Secure coding standards & TDD gate
│   ├── hooks.json                  # Agent tool call approval hooks
│   ├── scripts/validate_tool_call.py  # Blocks destructive tool calls
│   └── skills/stride-threat-model/ # STRIDE assessment skill definition
├── deployment/terraform/           # GCP infrastructure as code
├── .semgrep/rules.yaml             # Custom security scanning rules
├── .pre-commit-config.yaml         # Pre-commit: format + Semgrep scan
├── render.yaml                     # Render cloud deployment config
└── threat_model.md                 # Full STRIDE threat assessment
```

---

## 🔐 Security Architecture

This project implements all six **STRIDE** threat categories as code:

| STRIDE Threat | Exploit Scenario | Defense Applied |
|---|---|---|
| **Spoofing** | Unregistered user claims to be `user_001` | User identity allowlist check before every tool |
| **Tampering** | Two threads race to redeem the same code twice | `threading.Lock()` atomic check-and-flip |
| **Repudiation** | No record of who redeemed which code | Structured audit logging on every success |
| **Info Disclosure** | Error messages echo raw user input | Sanitized generic error messages |
| **Denial of Service** | Brute-force 10,000 code guesses per minute | Sliding-window rate limiter (5 attempts/60s per user) |
| **Elevation of Privilege** | Guest user redeems discount for free | Registered-user check before code access |

---

## 🧪 Test Suite

```
tests/test_agent.py — 33 security & business logic tests
├── Group 1: Happy Path                    ✅
├── Group 2: Pydantic Input Validation     ✅ (SQL injection, regex, length)
├── Group 3: Rate Limiting                 ✅ (per-user sliding window)
├── Group 4: Identity & Authorization      ✅ (spoofing, unregistered users)
├── Group 5: Code Existence Validation     ✅ (unknown codes)
├── Group 6: Single-Use Enforcement        ✅ (atomic double-redemption)
├── Group 7: Input Normalization           ✅ (case insensitivity)
├── Group 8: Error Sanitization            ✅ (no raw input echoed)
└── Group 9: Concurrency / Race Conditions ✅ (10 threads, 1 winner)
```

Run all tests:
```bash
uv run pytest tests/test_agent.py
```

---

## 🚀 Getting Started (Local Development)

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A [Gemini API Key](https://aistudio.google.com/apikey)

### 1. Clone the Repository
```bash
git clone https://github.com/SouravCodes23/shopping-assistant.git
cd shopping-assistant
```

### 2. Install Dependencies
```bash
uv sync
```

### 3. Set Up Environment Variables
```bash
cp .env.example .env
# Open .env and paste your GOOGLE_API_KEY
```

### 4. Run the Local Playground
```bash
uv run adk web . --host 127.0.0.1 --port 8080 --reload_agents
```

Then open your browser at: **http://127.0.0.1:8080/dev-ui/?app=app**

---

## 💬 Sample Prompts to Try

| What to Type | What It Tests |
|---|---|
| `What electronics products do you have?` | Product browsing |
| `Check the status of order ORD-1002` | Order lookup |
| `Redeem WELCOME50 for user_001` | Discount code redemption |
| `Award loyalty points to user_001 for order ORD-1004 with $299.99` | Loyalty points award |
| `Who is the president of France?` | Off-topic guardrail (agent will decline) |

---

## 🛠️ Available Commands

| Command | Description |
|---|---|
| `uv run adk web . --host 127.0.0.1 --port 8080` | Launch local playground |
| `uv run pytest tests/test_agent.py` | Run security test suite |
| `agents-cli lint` | Run all code quality checks |
| `agents-cli eval` | Evaluate agent behavior |

---

## 🏛️ Tech Stack

| Layer | Technology |
|---|---|
| **AI Model** | Google Gemini (`gemini-flash-latest`) |
| **Agent Framework** | Google ADK (Agent Development Kit) |
| **Input Validation** | Pydantic v2 |
| **Security Scanning** | Semgrep (pre-commit hook) |
| **Testing** | pytest (33 tests) |
| **Package Manager** | uv |
| **Code Quality** | Ruff (linting + formatting) |
| **Cloud Deployment** | Render / Google Cloud Agent Engine |

---

## 📄 License

Licensed under the [Apache 2.0 License](https://www.apache.org/licenses/LICENSE-2.0).
