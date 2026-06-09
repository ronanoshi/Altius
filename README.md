# Altius — Investor Document Platform

A full-stack web app that automates pulling files from an investor portal, classifying and extracting structured data from capital account statements, and surfacing the results through a holdings table and a RAG-powered chat interface.

---

## Setup & Run

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11 + |
| Node.js | 18 + |
| An OpenAI API key with credits | gpt-4o access |

### 1. Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (used as a fallback for portal auth if needed)
python -m playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env — fill in OPENAI_API_KEY, PORTAL_USERNAME, PORTAL_PASSWORD

# Start the API server
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### 3. First run

1. Open `http://localhost:5173`
2. Click **Sync Portal** in the nav bar
3. Watch the live progress stream — the pipeline runs crawl → classify → extract → embed
4. Navigate to **Holdings** to see extracted fund positions
5. Navigate to **Chat** to ask questions over the documents
6. Navigate to **Files** to browse everything that was downloaded

---

## Architecture

```
frontend/                     React + Vite + TypeScript
  src/
    pages/                    Holdings, Chat, Files
    components/SyncButton     SSE-based sync progress stream

backend/
  main.py                     FastAPI app, CORS, startup wiring
  app/
    config.py                 pydantic-settings — all config from .env
    database.py               SQLAlchemy + SQLite
    models/                   DownloadedFile, ExtractedStatement
    crawler/
      base.py                 BaseCrawler ABC (swap to Playwright if needed)
      httpx_crawler.py        Concrete: REST API + httpx downloads
      portal_client.py        Low-level portal API calls
    classifier/
      base.py                 BaseClassifier ABC
      hybrid.py               portal label → heuristic → LLM fallback
    extractor/
      base.py                 BaseExtractor ABC
      pdf_extractor.py        pdfplumber + PyMuPDF → GPT-4o structured output
    llm/
      base.py                 BaseLLMClient ABC (swap to Anthropic etc.)
      openai_client.py        chat_json() + chat() via OpenAI
    rag/
      chunker.py              Page-level PDF chunking (PyMuPDF)
      vector_store.py         ChromaDB wrapper, local ONNX embeddings
      pipeline.py             RAGPipeline: ingest + query + citation building
    api/
      deps.py                 FastAPI dependency providers (singletons)
      sync.py                 POST /api/sync  — full pipeline, SSE stream
      holdings.py             GET  /api/holdings
      files.py                GET  /api/files, GET /api/files/{id}/open
      chat.py                 POST /api/chat
```

**Data flow on Sync:**
1. `HttpxCrawler.sync` — logs in via `POST /api/v0.0.2/login`, lists deals and files, downloads new PDFs to `data/deal_{id}/`. Idempotency via `portal_file_id` in the DB.
2. `HybridClassifier.classify` — labels each `UNKNOWN` file. Portal's own `document_type` field (already has "Capital account") is the primary signal; filename patterns cover the rest; GPT-4o handles ambiguous cases.
3. `PDFExtractor.extract` — for each capital statement, pdfplumber extracts text + tables, GPT-4o returns `{fund_name, statement_date, current_value}` in structured JSON.
4. `RAGPipeline.ingest` — chunks every report and statement by page, embeds via ChromaDB's local ONNX model, stores in a persistent collection.

**Chat flow:**
- User question → ChromaDB cosine similarity search (top-8 chunks) → GPT-4o answer generation with citation instructions → response includes answer text + per-chunk citations with filename / page / period.
- Questions with no relevant corpus match (distance > 0.75) are answered honestly: "This information is not available in the provided documents."

---

## Key Design Decisions

### 1. Direct REST API instead of browser automation

When exploring the portal I intercepted its network traffic and discovered a clean REST API at `fo1.api.altius.finance`. The login, deal listing, and file listing are all simple JSON endpoints. The files themselves are served via pre-signed S3 URLs returned inline.

This meant the crawler could be implemented in ~100 lines of pure `httpx` rather than a Playwright browser session. It is faster (no headless browser startup), easier to test with mocks, and more reliable. Playwright remains available behind the `BaseCrawler` interface if the portal ever moves to a JS-only auth flow.

### 2. Hybrid classification — zero LLM calls for the common case

The portal already tags its own files with a `document_type` field ("Capital account" for statements). That alone covers 8 of 40 files at 0.95 confidence. Filename patterns (regex on "statement", "CAS", "commentary", "update", etc.) cover another 30. Only genuinely ambiguous files — in the test set, a cryptic reference-number filename and a capital call notice — are sent to GPT-4o. The system never silently buckets low-confidence files; they surface as `UNKNOWN`.

### 3. LLM extraction handles heterogeneous layouts better than regex

Capital account statements across six funds use at least five different labels for the same concept ("Ending NAV", "Closing net asset value", "Partner's Capital — Ending", "Net Capital", "Capital Account Value"). A regex or keyword approach requires enumerating these in advance and breaks on novel layouts. Sending pdfplumber-extracted text + tables to GPT-4o with a structured output schema gives consistent results across all layouts, at roughly $0.01 per document.

### 4. Local embeddings keep ingestion free; GPT-4o only for answer generation

ChromaDB ships with an ONNX-based `all-MiniLM-L6-v2` embedding model that runs locally with no API calls. The full 40-document corpus (88 chunks) ingests in ~60 seconds at zero LLM cost. GPT-4o is only invoked when the user actually sends a chat message. This matters both for cost and for latency during the sync step.

---

## What I'd Improve with More Time

- **Chunking strategy**: Page-level chunks are a good baseline but miss cross-page context. Overlapping sliding-window chunks or heading-aware splitting (detecting section titles) would improve retrieval quality for multi-page reports.

- **Re-ranking**: Before sending to GPT-4o, run a cross-encoder re-ranker on the top-20 retrieved chunks to select the 5 most relevant. This cuts hallucination risk and token cost.

- **Portal pagination**: The current `list_files` call assumes all files come back in a single response. Real portals paginate; add cursor/offset handling before deploying against a larger fund.

- **Transactional sync**: If extraction fails mid-run, the DB is left in a partially-processed state. Wrapping each file's classify-extract-ingest steps in a DB savepoint would make partial failures recoverable.

- **Statement extraction verification**: Spot-check extracted values against the raw `tags` JSON the portal already provides (`classification_data.Amount`). This would give a fast confidence signal without an extra LLM call.

- **Auth on the API**: The endpoints are currently unauthenticated. For a real deployment, add an API key or session token middleware.
