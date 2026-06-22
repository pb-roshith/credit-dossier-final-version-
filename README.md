<div align="center">

# 💳 Credit Dossier

**AI-Powered Credit Pitch Book Pipeline**

A full-stack platform that helps bank analysts generate credit dossiers and pitch books using Mistral AI — from document ingestion and OCR to narrative generation and multi-format export.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)](https://vite.dev)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)

</div>

---

## 📋 Overview

Credit Dossier streamlines the credit analysis workflow:

1. **Create a Deal** — Set up a new credit deal with borrower information
2. **Upload Documents** — Ingest PDFs, DOCX, XLSX, images (processed via Mistral OCR)
3. **Generate Narratives** — AI agents draft 16 standardized credit sections using grounding data
4. **Export** — Download completed pitch books as PDF, PowerPoint, or Word documents

## 🏗️ Architecture

```
credit-dossier/
├── backend/              # FastAPI + SQLAlchemy + Mistral AI
│   ├── app/
│   │   ├── agents/       # 16 section-specific AI agents
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── routers/      # REST API endpoints
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Business logic (ingestion, narrative, export)
│   │   └── main.py       # FastAPI entry point
│   └── requirements.txt
│
├── frontend/             # React + TanStack Router + Vite
│   ├── src/
│   │   ├── components/   # Reusable UI components (shadcn/ui)
│   │   ├── hooks/        # Custom React hooks
│   │   ├── lib/          # API clients and utilities
│   │   └── routes/       # File-based routing pages
│   └── package.json
│
├── .gitignore
├── .editorconfig
└── README.md
```

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Uvicorn |
| **Frontend** | React 19, TypeScript, TanStack Router, Vite 8 |
| **Styling** | Tailwind CSS 4, shadcn/ui, Radix UI |
| **AI** | Mistral AI SDK (OCR, Chat, Agents) |
| **Database** | SQLite (dev) / PostgreSQL (prod) |
| **Export** | ReportLab (PDF), python-pptx (PPTX), python-docx (DOCX) |

## 🚀 Getting Started

### Prerequisites

- **Python** 3.11+
- **Node.js** 18+
- **Mistral AI API Key** — Get one at [console.mistral.ai](https://console.mistral.ai)

### 1. Clone the Repository

```bash
git clone https://github.com/harshgurjar731/credit-dossier.git
cd credit-dossier
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (macOS/Linux)
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your MISTRAL_API_KEY

# Run the server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

The frontend will be available at `http://localhost:8080` and proxies API calls to the backend.

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET/POST` | `/api/deals` | List / Create deals |
| `GET/PUT/DELETE` | `/api/deals/{id}` | Deal CRUD |
| `POST` | `/api/deals/{id}/documents` | Upload document (OCR) |
| `POST` | `/api/deals/{id}/sections/{sid}/generate` | Generate narrative |
| `GET` | `/api/deals/{id}/export/{format}` | Export (pdf/pptx/docx) |

See the full API documentation at `/docs` when the backend is running.

## 🔐 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MISTRAL_API_KEY` | Mistral AI API key | ✅ |
| `DATABASE_URL` | Database connection string | ✅ (default: SQLite) |
| `APP_ENV` | `development` or `production` | ❌ |
| `UPLOAD_DIR` | File upload directory | ❌ (default: `./uploads`) |

## 📄 License

Private repository. All rights reserved.
