# Artech Solutions — RBAC-Aware Enterprise RAG System

An on-premises Role-Based Access Control (RBAC) RAG system built for the Artech Solutions hiring assignment. The system lets employees query a company knowledge base and enforces strict per-role document access — entirely locally, with no external APIs.

---

## Quick Start

### Prerequisites

- **Python 3.11**
  - Check with: `python3.11 --version`
  - Install via Homebrew if needed: `brew install python@3.11`
- [Ollama](https://ollama.com) installed and running
- Models pulled:
  - LLM: `ollama pull qwen2.5:3b`
  - Embeddings: `ollama pull nomic-embed-text`

### Setup

```bash
# 1. Clone/copy this folder
cd submission

# 2. Create virtual environment (must use Python 3.11)
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run ingestion (only needed once, or when corpus changes)
python src/ingest.py

# 5. Run a query
python src/main.py --role employee --user-id emp_001 --query "What is my leave balance?"
```

### Roles and User IDs

| Role | Example User IDs | Access |
|------|-----------------|--------|
| `admin` | `adm_001` | Finance: Full, Legal: Full, HR: Full |
| `manager` | `mgr_001` | Finance: Full, Legal: Summary, HR: Full |
| `employee` | `emp_001`, `emp_002` | Finance: None, Legal: None, HR: Own records |
| `auditor` | `aud_001` | Finance: Full, Legal: Full, HR: None |

### Example Commands

```bash
# Employee asking about leave
python src/main.py --role employee --user-id emp_001 --query "What is my leave balance?"

# Employee attempting to see severance (should be refused)
python src/main.py --role employee --user-id emp_001 --query "What is the severance structure?"

# Manager asking about legal docs (gets summary only)
python src/main.py --role manager --user-id mgr_001 --query "What does the NDA say about IP?"

# Admin — full access
python src/main.py --role admin --user-id adm_001 --query "What was Q3 profit and what does the employment contract say about non-compete?"

# Auditor asking about HR (should be refused)
python src/main.py --role auditor --user-id aud_001 --query "What are the employee salaries?"

# Interactive mode (no --query flag)
python src/main.py --role manager --user-id mgr_001

# Suppress retrieval trace (just the answer)
python src/main.py --role admin --user-id adm_001 --query "What is the travel reimbursement limit?" --no-trace

# Interactive Web Playground (starts local dashboard at http://localhost:8000)
python src/app.py
```

---

## Project Structure

```
submission/
├── requirements.txt
├── README.md
├── CONTACT.txt
├── src/
│   ├── config.py          # RBAC permission matrix + system config
│   ├── ingest.py          # Document chunking, embedding, Chroma ingestion
│   ├── rbac.py            # RBACRetriever + rbac_filter function
│   ├── prompts.py         # System prompt template (Layer 2 guardrail)
│   ├── chain.py           # LCEL chain + run_query with trace output
│   ├── main.py            # CLI entrypoint
│   ├── corpus/            # Synthetic document corpus (9 docs)
│   │   ├── finance_q3_report.txt
│   │   ├── finance_budget_forecast.txt
│   │   ├── finance_expense_policy.txt
│   │   ├── legal_employment_contract.txt
│   │   ├── legal_data_privacy_policy.txt
│   │   ├── legal_ip_nda.txt
│   │   ├── hr_leave_policy.txt
│   │   ├── hr_severance_policy.txt
│   │   ├── hr_employee_record_emp001.txt
│   │   └── hr_employee_record_emp002.txt
│   └── vectorstore/       # Auto-created by ingest.py (ChromaDB persistent)
└── docs/
    ├── task2_prompt_design.md
    ├── task3_adversarial_tests.md
    └── task4_client_brief.md
```

---

## Stack Choices and Rationale

### LangChain (LCEL)
Used LangChain for the pipeline because:
- LCEL chains are composable and each step is individually testable
- `BaseRetriever` subclassing gives a clean, interview-explainable RBAC integration point
- `ChatPromptTemplate` separates concerns — prompt design lives in `prompts.py`, not scattered in chain logic
- Avoided LangChain agents/tools — overkill for this use case and adds unpredictable behavior

### ChromaDB
Chosen over FAISS because:
- Native metadata persistence — RBAC tags survive restarts without manual serialization
- `similarity_search(query, k=K)` returns full metadata on each Document, needed for RBAC filter
- FAISS requires post-retrieval filtering, meaning restricted docs are retrieved then discarded — wasteful and a potential attack surface
- Chroma runs fully embedded (no server needed for local use)

### `nomic-embed-text` via Ollama
- High-performance local text embedding model (8192 context window)
- Runs completely on-premises via local Ollama instance (same runtime as Qwen)
- No API key, no network calls — zero external dependencies, fits enterprise constraints exactly

### Qwen 2.5:3b via Ollama
- Specified by the assignment
- Low temperature (0.1) used to maximize factuality and minimize hallucination
- 3B models are less instruction-following than 7B+, which is why Layer 1 (retrieval filter) is the real security boundary and not the prompt

---

## RBAC Design

Two-layer defense:

**Layer 1 — `RBACRetriever` in `rbac.py`**
The `RBACRetriever._get_relevant_documents()` calls Chroma, gets raw docs, then passes them through `rbac_filter()`. This function inspects each doc's metadata (`department`, `access_level`, `employee_id`) and applies the permission matrix. Restricted chunks never reach the LLM.

**Layer 2 — System prompt in `prompts.py`**
Even if a chunk slips through (e.g., metadata tagging error), the system prompt instructs the LLM to refuse disclosure. Rules are numbered, directive, and explicitly name known attack patterns (prompt injection, role impersonation).

Permission matrix:
```python
PERMISSIONS = {
    "admin":    {"Finance": "full",    "Legal": "full",    "HR": "full"},
    "manager":  {"Finance": "full",    "Legal": "summary", "HR": "full"},
    "employee": {"Finance": "none",    "Legal": "none",    "HR": "own_only"},
    "auditor":  {"Finance": "full",    "Legal": "full",    "HR": "none"},
}
```

Legal documents are chunked into two types: a `summary` chunk (the overview section, tagged `access_level=summary`) and `full` chunks (detailed clauses, tagged `access_level=full`). Managers get only summary chunks; admin and auditor get all chunks.

---

## Known Limitations and What I'd Do Differently

### 1. `own_only` HR access is too restrictive
The current implementation: `own_only` passes only chunks where `employee_id == user_id`. General HR policy documents (leave policy, severance) have no `employee_id` tag, so employees can't access them at all — not even their own leave *policy*, only their leave *balance*.

**What I'd do differently:** Split HR into two sub-categories: `HR_policy` (accessible to all employees) and `HR_personal` (own-only). The permission matrix would have separate entries. This tradeoff is intentional for the assignment to make the behavior observable.

### 2. No authentication layer
This system takes `--role` and `--user-id` as CLI arguments — trusting the caller completely. In production, roles and user IDs would come from a verified JWT or SSO token, never from user-supplied CLI input.

### 3. Chunk size tuning
`chunk_size=600` was chosen empirically. With more time and a larger corpus, I'd benchmark retrieval quality at 400, 600, and 800 tokens and measure answer faithfulness.

### 4. No re-ranking
After retrieval and RBAC filtering, chunks are passed to the LLM in raw retrieval order. Adding a cross-encoder re-ranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) would improve answer quality for multi-hop questions.

### 5. No streaming
Responses from Ollama are returned synchronously. For a real UI, streaming would dramatically improve perceived latency on a 3B model.

---

## What Is Working

- [x] Task 1: Full ingestion pipeline, RBAC-aware retrieval, LLM response generation
- [x] Task 2: Prompt design, live scenario documented with actual trace output
- [x] Task 3: 12+ adversarial tests across all 4 roles, documented with results and fixes
- [x] Task 4: Client brief for non-technical stakeholders

## What Is Not Implemented

- Authentication middleware (JWT/SSO) — documented as known limitation
- Re-ranking layer — documented as future improvement
- Streaming API — documented as future improvement
- Web UI — CLI only
