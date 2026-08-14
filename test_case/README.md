# Credit Dossier critical test suite

From the repository root, run:

```powershell
.\test_case\run_tests.ps1
```

Or run the folder directly with the project interpreter:

```powershell
.\backend\venv\Scripts\python.exe .\test_case
```

The default run checks:

- Python source compilation for the backend and local MCP server
- password hashing, password policy, sessions, and role permissions
- deal creation, the 16 default dossier sections, visibility, editing, status, and deletion
- text-document ingestion, deduplication, section linking, and unlinking
- narrative source normalization and export cleanup
- critical API route registration and OpenAPI generation
- production builds for both frontend applications

Tests use a fresh in-memory SQLite database and placeholder service settings.
They do not change the application database or call Mistral, MCP, or other
external services.

For a faster backend-only run, skip frontend builds:

```powershell
.\test_case\run_tests.ps1 --quick
```
