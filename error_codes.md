# Application error-code book

Every API failure uses the following JSON envelope:

```json
{
  "error_code": "AUTH-001",
  "detail": "Invalid user ID or password.",
  "event_id": "4f213cc8-2446-44a0-8977-aed706de32b7"
}
```

`error_code` is stable and suitable for client logic and support procedures. `event_id`
correlates the response to the server audit trail. Messages are canonical and contain no
internal exception, SQL, source-path, stack-trace, or upstream-response details.

| Code | HTTP | Canonical message | Meaning |
|---|---:|---|---|
| `REQ-001` | 422 | The request contains invalid data. | Request schema validation failed. |
| `REQ-002` | 400 | The request could not be processed. | Generic invalid request. |
| `AUTH-001` | 401 | Invalid user ID or password. | Credential verification failed. |
| `AUTH-002` | 403 | Your account is in the admin queue for approval. | Account approval is pending. |
| `AUTH-003` | 401 | Please sign in to continue. | No valid session was supplied. |
| `AUTH-004` | 401 | Your session is invalid. Please sign in again. | Session identifier was not recognized. |
| `AUTH-005` | 401 | Your session has expired. Please sign in again. | Session lifetime elapsed. |
| `AUTH-006` | 401 | This user account is inactive. | Account is inactive or unapproved. |
| `AUTH-007` | 403 | You do not have permission to perform this action. | Role authorization failed. |
| `AUTH-008` | 400 | The password does not satisfy the configured policy. | Password policy validation failed. |
| `AUTH-009` | 423 | Your account is locked. Reset your password using your security questions or contact an administrator. | Three consecutive credential failures locked the account. |
| `USER-001` | 409 | That user ID is already registered. | User identifier conflict. |
| `USER-002` | 404 | User ID was not found. | User lookup failed. |
| `USER-003` | 409 | This account is already approved. | Account approval conflict. |
| `USER-004` | 409 | This account is inactive. | Inactive account cannot be approved. |
| `DEAL-001` | 404 | Deal not found. | Deal lookup failed. |
| `SECTION-001` | 404 | Section not found. | Section lookup failed. |
| `DOCUMENT-001` | 404 | Document not found. | Document lookup failed. |
| `UPLOAD-001` | 404 | Upload not found. | Upload lookup failed. |
| `VERSION-001` | 404 | Version not found. | Version lookup failed. |
| `JOB-001` | 404 | Generation job not found. | Background generation job lookup failed. |
| `RESOURCE-001` | 404 | The requested resource was not found. | Generic resource lookup failed. |
| `STATE-001` | 409 | The operation conflicts with the current resource state. | Resource state conflict. |
| `FILE-001` | 400 | The uploaded file is invalid or unsupported. | File allowlist or signature validation failed. |
| `LIBRARY-001` | 404 | Library file not found. | Library document lookup failed. |
| `LIBRARY-002` | 409 | The document library is still synchronizing. | Library synchronization blocks the operation. |
| `LIBRARY-003` | 502 | The document library is temporarily unavailable. | Library initialization or access failed. |
| `GEN-001` | 400 | Section generation could not be completed with the supplied inputs. | Generation input validation failed. |
| `GEN-002` | 500 | Content generation failed. | Unexpected content-generation failure. |
| `DB-001` | 409 | The request conflicts with existing data. | Database integrity constraint failed. |
| `DB-002` | 400 | One or more supplied values are invalid. | Database rejected supplied data. |
| `DB-003` | 503 | The database is temporarily unavailable. Please try again. | Database operational failure. |
| `DB-004` | 500 | A database operation failed. | Unhandled database failure. |
| `EXT-001` | 504 | An external service timed out. Please try again. | Upstream timeout. |
| `EXT-002` | 502 | An external service is unavailable. Please try again. | Upstream HTTP failure. |
| `SYS-001` | 500 | An unexpected server error occurred. | Unhandled application failure. |

The executable source of truth is `backend/app/error_catalog.py`. Update the source and
this book together whenever a new failure class is introduced. Codes must never be
reused for a different meaning.
