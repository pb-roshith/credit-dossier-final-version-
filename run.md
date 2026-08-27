# Run Credit Dossier locally

Run PostgreSQL first and then open three PowerShell terminals from the repository
root.

The services use separate PostgreSQL databases:

- Backend application: `credit_dossier_backend`
- Local MCP: `credit_dossier_mcp`

## Terminal 1 — Local MCP server

```powershell
cd mcp
& ..\backend\venv\Scripts\python.exe server.py
```

The local MCP server runs at:

```text
http://127.0.0.1:8001/sse
```

## Terminal 2 — Backend

```powershell
cd backend
& .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend API documentation:

```text
http://127.0.0.1:8000/docs
```

## Terminal 3 — Frontend

```powershell
cd frontend
npm run dev
```

Open the application at:

```text
http://localhost:8080
```

## First-time dependency installation

Backend and MCP:

```powershell
python -m venv backend\venv
& .\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& .\backend\venv\Scripts\python.exe -m pip install -r mcp\requirements.txt
```

Frontend:

```powershell
cd frontend
npm install
```

## Verify the local MCP

With the MCP server running:

```powershell
$env:MCP_SSE_URL="http://127.0.0.1:8001/sse"
& .\backend\venv\Scripts\python.exe backend\test_mcp.py
```

The `.env` files contain secrets and are ignored by Git. Do not commit them.

## Optional: manufacture a detailed test company from MCP

There is no manufacturing page in the frontend. To add another sample company, run:

```powershell
cd mcp
& ..\backend\venv\Scripts\python.exe manufacture.py `
  --company-name "Aster Auto Components Limited" `
  --industry "Auto components manufacturing" `
  --geography "Pune, India"
```

The Mistral path makes multiple detailed-generation calls, so a complete
17-document run can take several minutes. Running the same company again
refreshes older PDFs and all 16 PostgreSQL datasets.

Test link (pqrs client ,ration analysis) - [dpaste.com/6E6QD7PTX](https://dpaste.com/6E6QD7PTX)
