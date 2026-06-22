/**
 * API client for Credit Dossier backend.
 * Supports Mistral Library + Agents architecture.
 */

const API_BASE = "/api";

// ── Types ──────────────────────────────────────────────────────

export type Status = "Draft" | "In Progress" | "In Review" | "Approved" | "Exported";
export type DealType = "Existing" | "New-to-bank";

export type UploadBrief = {
  id: string;
  source_type: string;
  filename: string | null;
  url: string | null;
  note: string | null;
  created_at: string;
};

export type DealDocument = {
  id: string;
  source_type: string;
  filename: string | null;
  url: string | null;
  note: string | null;
  extraction_method: string | null;
  page_count: number | null;
  created_at: string;
};

export type SectionDocumentLink = {
  id: string;
  document: DealDocument;
  created_at: string;
};

export type LibraryFile = {
  id: string;
  mistral_file_id: string;
  filename: string;
  source_type: string;
  file_size: number | null;
  note: string | null;
  created_at: string;
};

export type Section = {
  id: string;
  section_key: string;
  title: string;
  description: string;
  sources: string;
  expected_output: string;
  optional: boolean;
  state: "pending" | "ready";
  order_index: number;
  generated_content: string | null;
  custom_instructions: string | null;
  accuracy_score: number | null;
  accuracy_details: {
    score: number;
    grounded_claims: number;
    inferred_claims: number;
    unsupported_claims: number;
    summary: string;
  } | null;
  output_template: string | null;
  template_file_path: string | null;
  uploads: UploadBrief[]; // Legacy
  document_links: SectionDocumentLink[]; // Legacy
};

export type AuditEntry = {
  id: string;
  action: string;
  subject: string;
  user: string;
  created_at: string;
};

export type Version = {
  id: string;
  notes: string;
  status: string;
  created_at: string;
};

export type Deal = {
  id: string;
  customer: string;
  customer_type: DealType;
  industry: string;
  segment: string;
  geography: string;
  city: string;
  sector: string;
  kyc: "verified" | "pending";
  facility: string;
  currency: string;
  amount: number;
  tenure: number;
  pricing: string;
  repayment: string;
  collateral: boolean;
  due: string;
  owner: string;
  status: Status;
  created_at: string;
  updated_at: string;
  primary_color?: string;
  secondary_color?: string;
  theme_palette?: string[];
  mistral_library_id?: string | null;
  sections: Section[];
  documents: DealDocument[]; // Legacy
  library_files: LibraryFile[]; // Mistral Library
  audit_entries: AuditEntry[];
  versions: Version[];
};

export type DealListItem = Omit<Deal, "sections" | "audit_entries" | "versions" | "documents" | "library_files"> & {
  sections_ready: number;
  sections_total: number;
  versions_count: number;
};

export type DealCreate = {
  customer: string;
  customer_type?: string;
  industry?: string;
  segment?: string;
  geography?: string;
  kyc?: string;
  facility?: string;
  currency?: string;
  amount?: number;
  tenure?: number;
  pricing?: string;
  repayment?: string;
  collateral?: boolean;
  due?: string;
};

export type NarrativeResponse = {
  section_id: string;
  section_key: string;
  title: string;
  generated_content: string;
  state: string;
  accuracy_score: number | null;
  accuracy_details: {
    score: number;
    grounded_claims: number;
    inferred_claims: number;
    unsupported_claims: number;
    summary: string;
  } | null;
};

export type DraftAllResponse = {
  results: NarrativeResponse[];
  total: number;
  succeeded: number;
  failed: number;
};

// ── Fetch helpers ──────────────────────────────────────────────

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options?.headers as Record<string, string>) },
    ...options,
  });
  if (!res.ok) {
    const errBody = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${errBody}`);
  }
  // Handle 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── API Methods ────────────────────────────────────────────────

export const api = {
  // Health
  health: () => request<{ status: string }>(`${API_BASE}/health`),

  // Deals
  deals: {
    list: (params?: { status?: string; search?: string }) => {
      const qs = new URLSearchParams();
      if (params?.status && params.status !== "all") qs.set("status", params.status);
      if (params?.search) qs.set("search", params.search);
      const query = qs.toString();
      return request<DealListItem[]>(`${API_BASE}/deals${query ? `?${query}` : ""}`);
    },
    get: (id: string) => request<Deal>(`${API_BASE}/deals/${id}`),
    create: (data: DealCreate) =>
      request<Deal>(`${API_BASE}/deals`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Deal>) =>
      request<Deal>(`${API_BASE}/deals/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      request<void>(`${API_BASE}/deals/${id}`, { method: "DELETE" }),
  },

  // Sections
  sections: {
    list: (dealId: string) =>
      request<Section[]>(`${API_BASE}/deals/${dealId}/sections`),
    update: (dealId: string, sectionId: string, data: { expected_output?: string; custom_instructions?: string; state?: string; output_template?: string | null }) =>
      request<Section>(`${API_BASE}/deals/${dealId}/sections/${sectionId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    generate: (dealId: string, sectionId: string, customInstructions?: string) =>
      request<NarrativeResponse>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/generate`, {
        method: "POST",
        body: JSON.stringify({ custom_instructions: customInstructions || null }),
      }),
    generateAll: (dealId: string) =>
      request<DraftAllResponse>(`${API_BASE}/deals/${dealId}/sections/generate-all`, {
        method: "POST",
      }),
    uploadTemplate: async (dealId: string, sectionId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/sections/${sectionId}/template`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Template upload failed: ${res.status}`);
      return res.json() as Promise<Section>;
    },
    deleteTemplate: (dealId: string, sectionId: string) =>
      request<Section>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/template`, {
        method: "DELETE",
      }),
  },

  // Mistral Document Library (NEW)
  library: {
    list: (dealId: string) =>
      request<LibraryFile[]>(`${API_BASE}/deals/${dealId}/library`),
    upload: async (dealId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/library`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Library upload failed: ${res.status}`);
      return res.json() as Promise<LibraryFile>;
    },
    delete: (dealId: string, fileId: string) =>
      request<void>(`${API_BASE}/deals/${dealId}/library/${fileId}`, { method: "DELETE" }),
    initialize: (dealId: string) =>
      request<{ library_id: string; agents_created: number; agent_keys: string[] }>(
        `${API_BASE}/deals/${dealId}/library/initialize`,
        { method: "POST" }
      ),
  },

  // Versions
  versions: {
    submit: (dealId: string, notes: string) =>
      request<Version>(`${API_BASE}/deals/${dealId}/versions`, {
        method: "POST",
        body: JSON.stringify({ notes }),
      }),
    approve: (dealId: string, versionId: string) =>
      request<Version>(`${API_BASE}/deals/${dealId}/versions/${versionId}/approve`, {
        method: "PATCH",
      }),
  },

  // Deal Documents (Legacy — kept for backward compat)
  documents: {
    list: (dealId: string) =>
      request<DealDocument[]>(`${API_BASE}/deals/${dealId}/documents`),
    upload: async (dealId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/documents`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json() as Promise<DealDocument>;
    },
    delete: (dealId: string, docId: string) =>
      request<void>(`${API_BASE}/deals/${dealId}/documents/${docId}`, { method: "DELETE" }),
    linkToSection: (dealId: string, sectionId: string, documentIds: string[]) =>
      request<SectionDocumentLink[]>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/documents/link`, {
        method: "POST",
        body: JSON.stringify({ document_ids: documentIds }),
      }),
    unlinkFromSection: (dealId: string, sectionId: string, docId: string) =>
      request<void>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/documents/${docId}/unlink`, {
        method: "DELETE",
      }),
  },

  // Uploads (Legacy)
  uploads: {
    list: (dealId: string, sectionId: string) =>
      request<UploadBrief[]>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/uploads`),
    create: async (dealId: string, sectionId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/sections/${sectionId}/uploads`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json() as Promise<UploadBrief>;
    },
    delete: (uploadId: string) =>
      request<void>(`${API_BASE}/uploads/${uploadId}`, { method: "DELETE" }),
  },

  // Exports
  exports: {
    download: async (dealId: string, format: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/export/${format}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const contentDisposition = res.headers.get("content-disposition");
      const filename = contentDisposition?.match(/filename="(.+)"/)?.[1]
        || `PitchBook.${format}`;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
    generateReport: async (dealId: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/report`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Report generation failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "CreditReport.pdf";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
  },
};

// ── Utility ────────────────────────────────────────────────────

export function formatAmount(n: number, currency: string) {
  if (currency === "INR") {
    const cr = n / 10000000;
    return `INR ${cr.toFixed(2)} Cr`;
  }
  return `${currency} ${n.toLocaleString()}`;
}
