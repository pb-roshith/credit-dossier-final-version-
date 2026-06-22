# System Architecture

The following diagram illustrates the high-level architecture of the Credit Dossier platform, using **Mistral's Document Library** for fully managed RAG.

```mermaid
graph TD
    %% Styling
    classDef frontend fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff;
    classDef backend fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff;
    classDef data fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff;
    classDef external fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff;
    classDef export fill:#ef4444,stroke:#b91c1c,stroke-width:2px,color:#fff;

    %% Users and Frontend
    User([Bank Analyst / User]) -->|Interacts with| UI(React Frontend\nTanStack Router + Vite):::frontend
    
    %% API Gateway / Backend Entry
    UI -->|REST API Calls\nProxied via Vite| API(FastAPI Application):::backend
    
    %% Backend Services Layer
    subgraph Backend ["Monolithic Backend Services"]
        API --> DealSvc(Deal Management Service)
        API --> IngestSvc(Ingestion Service)
        API --> NarrativeSvc(Narrative Generation Service)
        API --> ExportSvc(Document Export Service)
    end
    
    %% Data Persistence
    subgraph Data ["Data Layer"]
        DealSvc -->|CRUD| DB[(Relational DB\nSQLite / PostgreSQL)]:::data
        IngestSvc -->|Save File Metadata| DB
        IngestSvc -->|Save to Disk| Disk[(Local File Storage)]:::data
    end
    
    %% Mistral Document Library (Managed RAG)
    subgraph MistralRAG ["Mistral Managed RAG"]
        IngestSvc -->|"Upload Files\n(PDF, DOCX, XLSX, PPTX)"| MistralLib(Mistral Document Library):::external
        MistralLib -->|"Auto: OCR + Chunking\n+ Embedding + Indexing"| MistralIndex[(Mistral Vector Index)]:::external
        
        NarrativeSvc -->|"DocumentLibraryTool\n(library_ids)"| MistralChat(Mistral Chat API\nwith Auto-Retrieval):::external
        MistralIndex -.->|Retrieved Chunks\nInjected Automatically| MistralChat
        MistralChat -->|Generated Drafts| NarrativeSvc
    end
    
    %% Save results
    NarrativeSvc -->|Save drafts| DB
    
    %% Export outputs
    subgraph Export ["Export Engine"]
        ExportSvc -.->|Reads Narratives| DB
        ExportSvc -->|reportlab| PDF[PDF Pitch Book]:::export
        ExportSvc -->|python-pptx| PPT[PowerPoint]:::export
        ExportSvc -->|python-docx| DOCX[Word Document]:::export
    end
```

## How Mistral Document Library Works

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant FastAPI
    participant MistralLib as Mistral Library
    participant MistralChat as Mistral Chat

    Note over User,MistralChat: File Upload & Indexing Flow
    User->>Frontend: Upload PDF/DOCX/XLSX
    Frontend->>FastAPI: POST /api/deals/{id}/sections/{sid}/uploads
    FastAPI->>FastAPI: Ensure Mistral Library exists for deal
    FastAPI->>MistralLib: Upload document to library
    MistralLib->>MistralLib: OCR → Chunk → Embed → Index
    MistralLib-->>FastAPI: Return document_id
    FastAPI-->>Frontend: Upload complete

    Note over User,MistralChat: Narrative Generation Flow
    User->>Frontend: Click "Generate Draft"
    Frontend->>FastAPI: POST /api/deals/{id}/sections/{sid}/generate
    FastAPI->>MistralChat: chat.complete(tools=[DocumentLibraryTool])
    MistralChat->>MistralLib: Auto-retrieve relevant chunks
    MistralLib-->>MistralChat: Grounding data
    MistralChat->>MistralChat: Generate with context
    MistralChat-->>FastAPI: Generated narrative
    FastAPI-->>Frontend: Section updated with content
```

## Key Design Decisions

### Why Mistral Document Library over ChromaDB?

| Aspect | ChromaDB (Previous) | Mistral Document Library (Current) |
|---|---|---|
| **Setup** | Self-hosted vector DB, manual embedding | Zero-config, fully managed |
| **OCR** | Manual text extraction per format | Mistral OCR handles all formats |
| **Chunking** | Custom chunking logic | Automatic, optimized chunking |
| **Embedding** | Separate API calls to mistral-embed | Handled internally |
| **Retrieval** | Manual query + inject into prompt | Automatic via DocumentLibraryTool |
| **Maintenance** | Manage ChromaDB storage, backups | Cloud-managed by Mistral |

### Per-Deal Library Isolation
Each deal gets its own Mistral Document Library (`mistral_library_id` on the Deal model). This ensures:
- Documents from Deal A never leak into Deal B's generation
- Library cleanup when a deal is deleted
- Clear audit trail of which documents ground which narratives
