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

Test link (pqrs client ,ration analysis) - [dpaste.com/6E6QD7PT](https://dpaste.com/6E6QD7PTX)

DPAPI:

cd backend

python -m app.local_secrets .env backend `
  MISTRAL_API_KEY DATABASE_URL INITIAL_ADMIN_PASSWORD

python -m app.local_secrets ..\mcp\.env mcp `
  MISTRAL_API_KEY POSTGRES_PASSWORD

## Railway: reject malformed asset paths

For the frontend Railway service, use `frontend` as the service root, build with
`npm ci && npm run build`, and set the start command to `npm start`.
The deployment must include `scripts/` alongside `.output/`.
If a container copies only `.output`, also copy `scripts` and `package.json`.

The start script binds the validating gateway to Railway's `PORT` on `0.0.0.0`.
It runs the generated Nitro server on loopback only, using `APP_INTERNAL_PORT`
(default `3001`). If Railway's `PORT` is `3001`, set `APP_INTERNAL_PORT` to another
unused port. Directly starting `node .output/server/index.mjs` bypasses this protection.
Nitro forwards `/api/**` to the backend. The default backend origin is
`http://localhost:8000`. For a separate backend service, set `BACKEND_URL`
to its origin before building the frontend (for example, `https://backend.example`).
The target is included in the production build.
Keep the existing API routing/proxy arrangement; this gateway forwards accepted
requests, methods, bodies, cookies, and response headers to the frontend unchanged.

The strict HTTP parser rejects malformed request lines, including WebInspect's
raw-tab payload. Path validation rejects literal and percent-encoded control
characters, including nested encoding, before Nitro serves static assets.
Validation uses the original request target rather than a normalized URL.
Run the regression checks with `npm run test:request-security` in `frontend`.

After redeployment, rerun WebInspect check 11699 from report pages 59�60.
The raw-tab request and `%09` / `%2509` variants must return `400`, while the
normal asset must still load. Local verification does not establish Railway edge
behavior: if its proxy strips the malicious characters before forwarding, the
edge must also be configured to reject them; application code cannot reconstruct
a request target already changed by the proxy.
