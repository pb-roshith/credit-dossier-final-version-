import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState, useCallback } from "react";
import {
  ArrowLeft, FileText, Clock, Download, Sparkles, RefreshCw, Plus, TriangleAlert,
  Loader2, CheckCircle2, Upload, X, FileDown, BookOpenCheck, Trash2, FileType, Save,
  File as FileIcon, Link as LinkIcon, Type, Eye, EyeOff, BarChart3, Table as TableIcon,
  ShieldCheck, AlertTriangle, ChevronDown, ChevronUp, Info
} from "lucide-react";
import { api, formatAmount, type Deal, type Section } from "@/lib/deals";
import ReactMarkdown from "react-markdown";

export const Route = createFileRoute("/deals/$dealId")({
  head: () => ({ meta: [{ title: "Deal — Credit Pitch Book" }] }),
  component: DealDetail,
});

type Tab = "overview" | "narratives" | "versions" | "export";

function DealDetail() {
  const { dealId } = Route.useParams();
  const [tab, setTab] = useState<Tab>("overview");
  const [deal, setDeal] = useState<Deal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDeal = useCallback(() => {
    setLoading(true);
    api.deals.get(dealId)
      .then(setDeal)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  useEffect(() => { fetchDeal(); }, [fetchDeal]);

  if (loading) {
    return (
      <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
        <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" /> Loading deal…
        </div>
      </main>
    );
  }

  if (error || !deal) {
    return (
      <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
        <p className="text-sm">{error || "Deal not found."} <Link to="/" className="text-primary underline">Back to dashboard</Link></p>
      </main>
    );
  }

  const tabs: { id: Tab; label: string; Icon: typeof FileText }[] = [
    { id: "overview", label: "Overview", Icon: FileText },
    { id: "narratives", label: "Narratives", Icon: Sparkles },
    { id: "versions", label: "Versions", Icon: Clock },
    { id: "export", label: "Export", Icon: Download },
  ];

  return (
    <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
      <div className="mb-4">
        <Link to="/" className="inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-medium hover:bg-accent hover:text-accent-foreground">
          <ArrowLeft className="h-4 w-4" /> Dashboard
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
              {deal.customer_type === "Existing" ? "Existing customer" : "New-to-bank"}
            </span>
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">{deal.facility}</span>
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">Due {deal.due}</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{deal.customer}</h1>
          <p className="text-sm text-muted-foreground">{deal.sector} · {deal.city}</p>
        </div>
        <div className="text-right">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Facility</div>
          <div className="font-mono text-xl font-bold">{formatAmount(deal.amount, deal.currency)}</div>
          <div className="text-xs text-muted-foreground">{deal.tenure}M · {deal.pricing}</div>
        </div>
      </div>

      <div className="mb-6 flex flex-wrap gap-1 border-b">
        {tabs.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              tab === id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab deal={deal} refresh={fetchDeal} />}
      {tab === "narratives" && <NarrativesTab deal={deal} refresh={fetchDeal} />}
      {tab === "versions" && <VersionsTab deal={deal} refresh={fetchDeal} />}
      {tab === "export" && <ExportTab deal={deal} refresh={fetchDeal} />}
    </main>
  );
}

/* ── Overview Tab ───────────────────────────────────────────── */

function OverviewTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const ready = deal.sections.filter(s => !s.optional && s.state === "ready").length;
  const total = deal.sections.filter(s => !s.optional).length;
  
  const [extractingTheme, setExtractingTheme] = useState(false);
  
  const handleExtractTheme = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setExtractingTheme(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/deals/${deal.id}/theme/extract`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      refresh();
    } catch (err) {
      console.error("Theme extraction failed:", err);
      alert("Failed to extract theme. Try a different file.");
    } finally {
      setExtractingTheme(false);
      e.target.value = "";
    }
  };

  const handleColorChange = async (type: "primary_color" | "secondary_color", value: string) => {
    try {
      const res = await fetch(`/api/deals/${deal.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [type]: value }),
      });
      if (!res.ok) throw new Error("Failed to update color");
      refresh();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-4">
      <div className="doc-card">
        <div className="doc-section-header"><span>Client &amp; Facility Snapshot</span></div>
        <div className="grid gap-4 p-5 sm:grid-cols-3">
          {([
            ["Segment", deal.segment], ["Industry", deal.industry], ["Geography", deal.geography],
            ["KYC", deal.kyc], ["Facility", deal.facility], ["Amount", `${deal.currency} ${deal.amount.toLocaleString()}`],
            ["Tenure", `${deal.tenure} months`], ["Pricing", deal.pricing], ["Collateral", deal.collateral ? "Secured" : "Clean"],
          ] as const).map(([k, v]) => (
            <div key={k}>
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{k}</div>
              <div className="text-sm font-medium">{v}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="doc-card">
        <div className="doc-section-header"><Clock className="h-4 w-4 shrink-0" /><span>Recent Activity</span></div>
        <ul className="divide-y">
          {deal.audit_entries.slice().reverse().map(a => (
            <li key={a.id} className="flex items-start justify-between gap-4 p-4">
              <div>
                <div className="font-semibold">{a.action}</div>
                <div className="text-xs text-muted-foreground">{a.subject}</div>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                <div className="font-medium text-foreground">{a.user}</div>
                <div>{new Date(a.created_at).toLocaleString()}</div>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="doc-card">
        <div className="doc-section-header"><FileText className="h-4 w-4 shrink-0" /><span>Readiness</span></div>
        <div className="space-y-3 p-5">
          <div>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span>Mandatory sections ready</span>
              <span className="font-mono text-muted-foreground">{ready}/{total}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${total > 0 ? (ready / total) * 100 : 0}%` }} />
            </div>
          </div>
          {([
            ["Documents uploaded", deal.sections.reduce((sum, s) => sum + (s.uploads?.length || 0), 0), "bg-info/15 text-info"],
            ["Versions", deal.versions.length, "bg-muted text-muted-foreground"],
          ] as const).map(([label, v, cls]) => (
            <div key={String(label)} className="flex items-center justify-between border-t pt-3 text-sm">
              <span>{label}</span>
              <span className={`min-w-7 rounded-full px-2 py-0.5 text-center text-xs font-semibold ${cls as string}`}>{v as number}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="doc-card">
        <div className="doc-section-header"><Sparkles className="h-4 w-4 shrink-0 text-primary" /><span>Brand &amp; Theme Extraction</span></div>
        <div className="p-5">
          <p className="mb-4 text-sm text-muted-foreground">
            Upload an Annual Report or corporate presentation to let the AI automatically extract the company's brand colors. Or, manually set your preferred hex codes.
          </p>
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">Extract Theme</label>
              <label className="btn-primary inline-flex cursor-pointer items-center gap-2">
                {extractingTheme ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {extractingTheme ? "Extracting..." : "Upload Document"}
                <input type="file" className="hidden" accept=".pdf,.txt" onChange={handleExtractTheme} disabled={extractingTheme} />
              </label>
            </div>
            
            <div className="flex items-center gap-4">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">Primary Color</label>
                <div className="flex items-center gap-2 rounded-md border p-1 shadow-sm">
                  <input 
                    type="color" 
                    value={deal.primary_color || "#002060"} 
                    onChange={(e) => handleColorChange("primary_color", e.target.value)}
                    className="h-8 w-8 cursor-pointer rounded border-none p-0 outline-none"
                  />
                  <span className="font-mono text-sm font-medium">{deal.primary_color || "#002060"}</span>
                </div>
              </div>
              
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">Secondary Color</label>
                <div className="flex items-center gap-2 rounded-md border p-1 shadow-sm">
                  <input 
                    type="color" 
                    value={deal.secondary_color || "#800020"} 
                    onChange={(e) => handleColorChange("secondary_color", e.target.value)}
                    className="h-8 w-8 cursor-pointer rounded border-none p-0 outline-none"
                  />
                  <span className="font-mono text-sm font-medium">{deal.secondary_color || "#800020"}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Narratives Tab ─────────────────────────────────────────── */

function NarrativesTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const [activeId, setActiveId] = useState(deal.sections[0]?.id || "");
  const active = deal.sections.find(s => s.id === activeId);
  const [expected, setExpected] = useState(active?.expected_output || "");
  const [customInstructions, setCustomInstructions] = useState(active?.custom_instructions || "");
  const [outputTemplate, setOutputTemplate] = useState(active?.output_template || "");
  const [generating, setGenerating] = useState(false);
  const [draftingAll, setDraftingAll] = useState(false);
  const [uploadType, setUploadType] = useState<"file" | "url" | "text">("file");
  const [uploadNote, setUploadNote] = useState("");
  const [uploading, setUploading] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [textInput, setTextInput] = useState("");
  const [showInputs, setShowInputs] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [uploadingTemplate, setUploadingTemplate] = useState(false);
  const [showTemplatePreview, setShowTemplatePreview] = useState(false);

  // New Document Architecture State
  const [docTab, setDocTab] = useState<"existing" | "new">("existing");
  const [selectedDocsToLink, setSelectedDocsToLink] = useState<Set<string>>(new Set());
  const [linkingDocs, setLinkingDocs] = useState(false);

  useEffect(() => {
    if (active) {
      setExpected(active.expected_output);
      setCustomInstructions(active.custom_instructions || "");
      setOutputTemplate(active.output_template || "");
      setShowTemplatePreview(false);
      setSelectedDocsToLink(new Set()); // Reset selection on section change
    }
  }, [activeId, active]);

  const handleGenerate = async () => {
    if (!active || generating) return;
    setGenerating(true);
    try {
      await api.sections.generate(deal.id, active.id, customInstructions || undefined);
      refresh();
    } catch (err) {
      console.error("Generation failed:", err);
    } finally {
      setGenerating(false);
    }
  };

  const handleDraftAll = async () => {
    if (draftingAll) return;
    setDraftingAll(true);
    try {
      await api.sections.generateAll(deal.id);
      refresh();
    } catch (err) {
      console.error("Draft all failed:", err);
    } finally {
      setDraftingAll(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!active || uploading) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("source_type", uploadType);
      formData.append("note", uploadNote);

      if (uploadType === "file") {
        const fileInput = document.getElementById("section-file-input") as HTMLInputElement;
        if (!fileInput?.files?.[0]) return;
        formData.append("file", fileInput.files[0]);
      } else if (uploadType === "url") {
        formData.append("url", urlInput);
      } else {
        formData.append("text_content", textInput);
      }

      // New Flow: Upload to deal-level, then auto-link to current section
      const doc = await api.documents.upload(deal.id, formData);
      await api.documents.linkToSection(deal.id, active.id, [doc.id]);

      setUploadNote("");
      setUrlInput("");
      setTextInput("");
      setSelectedFileName("");
      setShowInputs(false);
      refresh();
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setUploading(false);
    }
  };

  const handleLinkExisting = async () => {
    if (!active || linkingDocs || selectedDocsToLink.size === 0) return;
    setLinkingDocs(true);
    try {
      await api.documents.linkToSection(deal.id, active.id, Array.from(selectedDocsToLink));
      setSelectedDocsToLink(new Set());
      setShowInputs(false);
      refresh();
    } catch (err) {
      console.error("Link documents failed:", err);
    } finally {
      setLinkingDocs(false);
    }
  };

  const handleUnlinkDocument = async (docId: string) => {
    if (!active) return;
    try {
      await api.documents.unlinkFromSection(deal.id, active.id, docId);
      refresh();
    } catch (err) {
      console.error("Unlink document failed:", err);
    }
  };

  const handleDeleteUpload = async (uploadId: string) => {
    try {
      await api.uploads.delete(uploadId);
      refresh();
    } catch (err) {
      console.error("Delete upload failed:", err);
    }
  };

  // ── Template handlers ──
  const handleSaveTemplate = async () => {
    if (!active || savingTemplate) return;
    setSavingTemplate(true);
    try {
      await api.sections.update(deal.id, active.id, { output_template: outputTemplate || null });
      refresh();
    } catch (err) {
      console.error("Save template failed:", err);
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleUploadTemplate = async () => {
    if (!active || uploadingTemplate) return;
    const fileInput = document.getElementById("template-file-input") as HTMLInputElement;
    if (!fileInput?.files?.[0]) return;
    setUploadingTemplate(true);
    try {
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      await api.sections.uploadTemplate(deal.id, active.id, formData);
      fileInput.value = "";
      refresh();
    } catch (err) {
      console.error("Template upload failed:", err);
    } finally {
      setUploadingTemplate(false);
    }
  };

  const handleDeleteTemplate = async () => {
    if (!active) return;
    try {
      await api.sections.deleteTemplate(deal.id, active.id);
      setOutputTemplate("");
      refresh();
    } catch (err) {
      console.error("Delete template failed:", err);
    }
  };

  if (!active) return null;

  const readySections = deal.sections.filter(s => s.state === "ready").length;
  const totalSections = deal.sections.length;
  const wordCount = active.generated_content ? active.generated_content.split(/\s+/).length : 0;
  const isFewShot = !!active.custom_instructions;
  const hasTemplate = !!active.output_template;
  const docCount = (active.document_links?.length || 0) + (active.uploads?.length || 0);

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      {/* ── Left Panel: Section List ── */}
      <div className="space-y-3">
        {/* Draft All Card */}
        <div className="doc-card">
          <div className="p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-medium text-muted-foreground">
                Progress: {readySections}/{totalSections} sections
              </div>
              <div className="text-xs font-mono text-muted-foreground">
                {totalSections > 0 ? Math.round((readySections / totalSections) * 100) : 0}%
              </div>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted mb-3">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${totalSections > 0 ? (readySections / totalSections) * 100 : 0}%` }}
              />
            </div>
            <button
              onClick={handleDraftAll}
              disabled={draftingAll}
              className="w-full inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60 transition-colors"
            >
              {draftingAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {draftingAll ? "Drafting all sections…" : "Draft All Sections"}
            </button>
          </div>
        </div>

        {/* Section List */}
        <div className="doc-card">
          <div className="doc-section-header"><span>Sections</span></div>
          <ul className="divide-y max-h-[500px] overflow-y-auto">
            {deal.sections.map((s, i) => (
              <li key={s.id}>
                <button
                  onClick={() => setActiveId(s.id)}
                  className={`flex w-full items-center justify-between px-3 py-2.5 text-left text-sm transition-colors ${
                    activeId === s.id
                      ? "bg-primary/5 border-l-2 border-l-primary"
                      : "hover:bg-surface border-l-2 border-l-transparent"
                  }`}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-[10px] text-muted-foreground shrink-0 w-5 text-right">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className={`font-medium truncate ${activeId === s.id ? "text-primary" : ""}`}>
                      {s.title}
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5 shrink-0 ml-2">
                    {/* Indicators */}
                    {s.uploads && s.uploads.length > 0 && (
                      <span className="rounded-full bg-blue-100 px-1.5 py-0.5 text-[9px] font-bold text-blue-700" title={`${s.uploads.length} document(s)`}>
                        {s.uploads.length}📄
                      </span>
                    )}
                    {s.output_template && (
                      <span className="rounded-full bg-violet-100 px-1 py-0.5 text-[9px] text-violet-700" title="Has template">
                        📋
                      </span>
                    )}
                    <span className={`section-status-badge ${s.state}`}>
                      {s.state === "ready" ? <CheckCircle2 className="h-3 w-3" /> : null}
                      {s.state}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── Right Panel: Section Detail ── */}
      <div className="space-y-4">
        {/* Section Header Card */}
        <div className={`doc-card ${active.generated_content ? "narrative-ready-glow" : ""}`}>
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <span className="font-mono text-xs opacity-70">
                {String(deal.sections.indexOf(active) + 1).padStart(2, "0")}
              </span>
              {active.title}
            </span>
            <div className="flex items-center gap-2">
              {/* Mode badges */}
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                isFewShot
                  ? "bg-amber-100 text-amber-800 border border-amber-200"
                  : "bg-slate-100 text-slate-600 border border-slate-200"
              }`}>
                {isFewShot ? "Few-shot" : "Zero-shot"}
              </span>
              {hasTemplate && (
                <span className="rounded-full bg-violet-100 text-violet-800 border border-violet-200 px-2 py-0.5 text-[10px] font-semibold">
                  Template
                </span>
              )}
              <span className={`section-status-badge ${active.state}`}>
                {active.state === "ready" ? <CheckCircle2 className="h-3 w-3" /> : null}
                {active.state}
              </span>
            </div>
          </div>
          <div className="p-4">
            <p className="text-sm text-muted-foreground">{active.description}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-md bg-surface p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Data Sources</div>
                <div className="text-xs">{active.sources}</div>
              </div>
              <div className="rounded-md bg-surface p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Expected Output</div>
                <div className="text-xs">{active.expected_output}</div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Grounding Data — Improved Document Upload ── */}
        <div className="doc-card">
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <Upload className="h-4 w-4 shrink-0" />
              Section Documents
              {docCount > 0 && (
                <span className="rounded-full bg-blue-500/20 text-blue-700 px-2 py-0.5 text-[10px] font-bold">
                  {docCount} file{docCount !== 1 ? "s" : ""}
                </span>
              )}
            </span>
            <button
              onClick={() => setShowInputs(!showInputs)}
              className={`inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-[11px] font-medium transition-colors ${
                showInputs
                  ? "border-red-300/50 bg-red-500/20 text-white hover:bg-red-500/30"
                  : "border-primary-foreground/30 bg-primary-foreground/15 text-primary-foreground hover:bg-primary-foreground/25"
              }`}
            >
              {showInputs ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
              {showInputs ? "Cancel" : "Add Document"}
            </button>
          </div>

          {showInputs && (
            <div className="p-4 bg-surface/50 border-b space-y-4">
              {/* Tabs */}
              <div className="flex gap-2 border-b border-border/50 pb-2">
                <button
                  type="button"
                  onClick={() => setDocTab("existing")}
                  className={`px-3 py-1 text-[11px] font-semibold uppercase tracking-wider rounded-md transition-colors ${
                    docTab === "existing" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Select Existing ({deal.documents?.length || 0})
                </button>
                <button
                  type="button"
                  onClick={() => setDocTab("new")}
                  className={`px-3 py-1 text-[11px] font-semibold uppercase tracking-wider rounded-md transition-colors ${
                    docTab === "new" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Upload New
                </button>
              </div>

              {docTab === "existing" && (
                <div className="space-y-3">
                  <div className="max-h-48 overflow-y-auto rounded-md border bg-background">
                    {deal.documents?.length === 0 ? (
                      <div className="p-4 text-center text-xs text-muted-foreground">No documents in deal library yet.</div>
                    ) : (
                      <ul className="divide-y">
                        {deal.documents?.map(doc => {
                          const isLinked = active.document_links?.some(l => l.document.id === doc.id);
                          const isSelected = selectedDocsToLink.has(doc.id);
                          return (
                            <li
                              key={doc.id}
                              className={`flex items-center px-3 py-2 cursor-pointer transition-colors ${
                                isLinked ? "bg-muted/30 opacity-70 cursor-not-allowed" : "hover:bg-muted/50"
                              }`}
                              onClick={() => {
                                if (isLinked) return;
                                const newSet = new Set(selectedDocsToLink);
                                if (isSelected) newSet.delete(doc.id);
                                else newSet.add(doc.id);
                                setSelectedDocsToLink(newSet);
                              }}
                            >
                              <input
                                type="checkbox"
                                className="mr-3 h-3.5 w-3.5"
                                checked={isLinked || isSelected}
                                disabled={isLinked}
                                readOnly
                              />
                              <div className="flex-1 min-w-0 flex items-center justify-between">
                                <div className="text-xs font-medium truncate">{doc.filename || doc.url || "Text Document"}</div>
                                <div className="text-[10px] text-muted-foreground flex gap-2">
                                  {doc.extraction_method === "mistral_ocr" && <span className="text-emerald-600 font-semibold">⚡ OCR</span>}
                                  <span>{doc.page_count} pg</span>
                                </div>
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                  <div className="flex justify-end">
                    <button
                      onClick={handleLinkExisting}
                      disabled={linkingDocs || selectedDocsToLink.size === 0}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                    >
                      {linkingDocs ? <Loader2 className="h-3 w-3 animate-spin" /> : <LinkIcon className="h-3 w-3" />}
                      Link Selected ({selectedDocsToLink.size})
                    </button>
                  </div>
                </div>
              )}

              {docTab === "new" && (
                <form onSubmit={handleUpload} className="space-y-3">
                  <div className="flex gap-1 rounded-lg bg-muted p-0.5">
                    {[
                      { type: "file" as const, label: "File", Icon: FileIcon },
                      { type: "url" as const, label: "URL", Icon: LinkIcon },
                      { type: "text" as const, label: "Text", Icon: Type },
                    ].map(({ type, label, Icon }) => (
                      <button
                        key={type}
                        type="button"
                        onClick={() => setUploadType(type)}
                        className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                          uploadType === type
                            ? "bg-background text-foreground shadow-sm"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        <Icon className="h-3 w-3" /> {label}
                      </button>
                    ))}
                  </div>

                  {uploadType === "file" && (
                    <div className="relative rounded-lg border-2 border-dashed border-muted-foreground/30 bg-muted/20 p-6 text-center hover:bg-muted/40 hover:border-primary/40 transition-colors cursor-pointer">
                      <input
                        type="file"
                        id="section-file-input"
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                        accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.csv,.txt,.md,.json"
                        onChange={(e) => setSelectedFileName(e.target.files?.[0]?.name || "")}
                      />
                      <FileIcon className={`h-8 w-8 mx-auto mb-3 ${selectedFileName ? 'text-primary' : 'text-muted-foreground/60'}`} />
                      {selectedFileName ? (
                        <div className="text-sm font-semibold text-primary break-all px-4">{selectedFileName}</div>
                      ) : (
                        <>
                          <div className="text-sm font-medium text-foreground mb-1">Click to browse or drag and drop</div>
                          <div className="text-[10px] text-muted-foreground">PDF, DOCX, XLSX, PPTX, CSV, TXT, MD</div>
                        </>
                      )}
                    </div>
                  )}
                  {uploadType === "url" && (
                    <input
                      placeholder="https://example.com/document.pdf"
                      value={urlInput}
                      onChange={e => setUrlInput(e.target.value)}
                      className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    />
                  )}
                  {uploadType === "text" && (
                    <textarea
                      placeholder="Paste document content here…"
                      value={textInput}
                      onChange={e => setTextInput(e.target.value)}
                      rows={4}
                      className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    />
                  )}

                  <div className="flex gap-2">
                    <input
                      placeholder="Note (optional)"
                      value={uploadNote}
                      onChange={e => setUploadNote(e.target.value)}
                      className="flex-1 h-9 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    />
                    <button
                      type="submit"
                      disabled={uploading}
                      className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60 transition-colors"
                    >
                      {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                      Upload & Link
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {docCount > 0 ? (
            <ul className="divide-y">
              {/* Render New Architecture Documents */}
              {active.document_links?.map(link => {
                const doc = link.document;
                const typeConfig: Record<string, { color: string; icon: string }> = {
                  file: { color: "bg-blue-100 text-blue-700 border-blue-200", icon: "📄" },
                  url: { color: "bg-green-100 text-green-700 border-green-200", icon: "🔗" },
                  text: { color: "bg-orange-100 text-orange-700 border-orange-200", icon: "📝" },
                };
                const cfg = typeConfig[doc.source_type] || typeConfig.file;

                return (
                  <li key={link.id} className="flex items-center justify-between px-4 py-2.5 hover:bg-surface/50 transition-colors group">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={`rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase shrink-0 ${cfg.color}`}>
                        {cfg.icon} {doc.source_type}
                      </span>
                      <div className="min-w-0">
                        <div className="text-xs font-medium truncate">
                          {doc.filename || doc.url || "Text document"}
                        </div>
                        <div className="text-[10px] text-muted-foreground flex gap-2 items-center">
                          {doc.extraction_method === "mistral_ocr" && <span className="text-emerald-600 font-semibold">⚡ OCR</span>}
                          {doc.page_count !== null && <span>{doc.page_count} pg</span>}
                          {doc.note && <span className="truncate max-w-[150px]">• {doc.note}</span>}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleUnlinkDocument(doc.id)}
                      className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all"
                      title="Unlink document from section"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </li>
                );
              })}
              
              {/* Render Legacy Uploads */}
              {active.uploads?.map(upl => {
                const typeConfig: Record<string, { color: string; icon: string }> = {
                  file: { color: "bg-slate-100 text-slate-700 border-slate-200", icon: "📄" },
                  url: { color: "bg-slate-100 text-slate-700 border-slate-200", icon: "🔗" },
                  text: { color: "bg-slate-100 text-slate-700 border-slate-200", icon: "📝" },
                };
                const cfg = typeConfig[upl.source_type] || typeConfig.file;

                return (
                  <li key={upl.id} className="flex items-center justify-between px-4 py-2.5 hover:bg-surface/50 transition-colors group">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={`rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase shrink-0 ${cfg.color}`}>
                        {cfg.icon} Legacy
                      </span>
                      <div className="min-w-0">
                        <div className="text-xs font-medium truncate">
                          {upl.filename || upl.url || "Text input"}
                        </div>
                        {upl.note && (
                          <div className="text-[10px] text-muted-foreground truncate">{upl.note}</div>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteUpload(upl.id)}
                      className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all"
                      title="Remove legacy upload"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : !showInputs ? (
            <div className="px-4 py-6 text-center">
              <Upload className="h-6 w-6 mx-auto mb-2 text-muted-foreground/40" />
              <div className="text-xs text-muted-foreground">
                No documents attached to this section.
              </div>
              <div className="text-[10px] text-muted-foreground/60 mt-1">
                Upload files to ground the AI agent with real data.
              </div>
            </div>
          ) : null}
        </div>

        {/* ── Custom Instructions (Few-shot) ── */}
        <div className="doc-card">
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              Custom Instructions for AI
              <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${
                customInstructions.trim()
                  ? "bg-amber-100 text-amber-800"
                  : "bg-muted text-muted-foreground"
              }`}>
                {customInstructions.trim() ? "Few-shot" : "Zero-shot"}
              </span>
            </span>
          </div>
          <div className="p-4">
            <textarea
              value={customInstructions}
              onChange={e => setCustomInstructions(e.target.value)}
              rows={3}
              placeholder={`Provide example output patterns for the AI to follow (few-shot approach).\n\nExample:\n"For the executive summary, start with a recommendation paragraph, then use bullet points for key highlights. Include a risk summary table at the end."`}
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <p className="text-[10px] text-muted-foreground mt-1.5">
              {customInstructions.trim()
                ? "✨ Few-shot mode — the agent will use your instructions as example patterns."
                : "No instructions set — the agent will run in zero-shot mode."}
            </p>
          </div>
        </div>

        {/* ── Output Template ── */}
        <div className="doc-card">
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <FileType className="h-4 w-4 shrink-0" />
              Output Template
              {hasTemplate && (
                <span className="rounded-full bg-violet-100 text-violet-700 px-2 py-0.5 text-[10px] font-bold">
                  Active
                </span>
              )}
            </span>
            <div className="flex items-center gap-1">
              {hasTemplate && (
                <>
                  <button
                    onClick={() => setShowTemplatePreview(!showTemplatePreview)}
                    className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] font-medium bg-primary-foreground/10 hover:bg-primary-foreground/20 transition-colors"
                    title={showTemplatePreview ? "Hide preview" : "Show preview"}
                  >
                    {showTemplatePreview ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                  </button>
                  <button
                    onClick={handleDeleteTemplate}
                    className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] font-medium text-destructive hover:bg-destructive/10 transition-colors"
                    title="Remove template"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </>
              )}
            </div>
          </div>
          <div className="p-4 space-y-3">
            {/* Template text preview */}
            {hasTemplate && showTemplatePreview && (
              <div className="rounded-md bg-violet-50 border border-violet-200 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-violet-600 mb-2">
                  Current Template Preview
                </div>
                <pre className="text-xs text-violet-900 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                  {active.output_template}
                </pre>
              </div>
            )}

            {/* Template textarea */}
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1.5">
                Paste or edit markdown template
              </label>
              <textarea
                value={outputTemplate}
                onChange={e => setOutputTemplate(e.target.value)}
                rows={4}
                placeholder={`# Section Heading\n\n## Sub-section 1\n- Key point 1\n- Key point 2\n\n## Sub-section 2\n| Column A | Column B |\n|----------|----------|\n| ...      | ...      |`}
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
              <button
                onClick={handleSaveTemplate}
                disabled={savingTemplate || outputTemplate === (active.output_template || "")}
                className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-md bg-violet-600 px-3 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-40 transition-colors"
              >
                {savingTemplate ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                Save Template
              </button>
            </div>

            {/* Divider */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t" /></div>
              <div className="relative flex justify-center text-[10px] uppercase">
                <span className="bg-card px-2 text-muted-foreground">or upload file</span>
              </div>
            </div>

            {/* Template file upload */}
            <div className="rounded-lg border-2 border-dashed border-violet-200 p-3 hover:border-violet-400 transition-colors">
              <div className="flex items-center gap-3">
                <FileType className="h-5 w-5 text-violet-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <input
                    type="file"
                    id="template-file-input"
                    accept=".md,.txt,.docx,.doc"
                    className="text-xs w-full"
                    onChange={handleUploadTemplate}
                  />
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Supports .md, .txt, .docx files
                  </p>
                </div>
                {uploadingTemplate && <Loader2 className="h-4 w-4 animate-spin text-violet-500" />}
              </div>
              {active.template_file_path && (
                <div className="mt-2 flex items-center gap-2 text-[10px] text-violet-600">
                  <CheckCircle2 className="h-3 w-3" />
                  Template loaded from file
                </div>
              )}
            </div>

            <p className="text-[10px] text-muted-foreground">
              The AI agent will follow this template's exact structure (headings, tables, bullet format) when generating the narrative.
            </p>
          </div>
        </div>

        {/* ── Generated Narrative — The Star of the Show ── */}
        <div className={`doc-card ${active.generated_content ? "narrative-ready-glow" : ""}`}>
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              Generated Narrative
              {active.generated_content && (
                <span className="rounded-full bg-primary-foreground/20 px-2 py-0.5 text-[10px] font-semibold">
                  {wordCount} words
                </span>
              )}
            </span>
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="inline-flex h-7 items-center gap-1 rounded-md border border-primary-foreground/30 bg-primary-foreground/10 px-2 text-xs font-medium disabled:opacity-60 hover:bg-primary-foreground/20 transition-colors"
            >
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {generating ? "Generating…" : "Generate"}
            </button>
          </div>

          {active.generated_content ? (
            <div className="narrative-content-enter">
              {/* Success banner */}
              <div className="flex items-center gap-2 px-5 py-2.5 bg-emerald-50 border-b border-emerald-100">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">
                  AI Draft Ready
                </span>
                <div className="ml-auto flex items-center gap-2">
                  {isFewShot && (
                    <span className="text-[9px] font-medium text-amber-700 bg-amber-50 rounded-full px-2 py-0.5 border border-amber-200">
                      Few-shot
                    </span>
                  )}
                  {hasTemplate && (
                    <span className="text-[9px] font-medium text-violet-700 bg-violet-50 rounded-full px-2 py-0.5 border border-violet-200">
                      Templated
                    </span>
                  )}
                  <span className="text-[10px] text-emerald-600">
                    {docCount > 0 ? `${docCount} doc(s) grounded` : "No docs"} · Mistral AI
                  </span>
                </div>
              </div>
              {/* Accuracy Panel */}
              <AccuracyPanel section={active} />
              {/* Rendered markdown content */}
              <div className="narrative-prose px-6 py-5">
                <MarkdownRenderer content={active.generated_content} primaryColor={deal.primary_color} secondaryColor={deal.secondary_color} />
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-4 p-12 text-center">
              <div className="rounded-full bg-muted p-4">
                <Sparkles className="h-8 w-8 text-muted-foreground" />
              </div>
              <div>
                <div className="font-semibold text-foreground">No AI draft yet</div>
                <div className="text-sm text-muted-foreground mt-1 max-w-sm">
                  Upload section documents, add custom instructions (few-shot), and optionally set an output template. Then generate the draft.
                </div>
              </div>
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-60 transition-colors"
              >
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {generating ? "Generating…" : "Generate Draft"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Accuracy Panel Component ──────────────────────────────────── */

function AccuracyPanel({ section }: { section: Section }) {
  const [expanded, setExpanded] = useState(false);

  // No accuracy assessment available
  if (section.accuracy_score === null && !section.accuracy_details) {
    return (
      <div className="flex items-center gap-2 px-5 py-2 bg-slate-50 border-b border-slate-100">
        <Info className="h-3.5 w-3.5 text-slate-400" />
        <span className="text-[10px] text-slate-500 italic">
          Accuracy not assessed — no grounding documents attached
        </span>
      </div>
    );
  }

  const score = section.accuracy_score ?? 0;
  const details = section.accuracy_details;

  // Color theming based on score
  const getScoreColor = (s: number) => {
    if (s >= 80) return { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", ring: "stroke-emerald-500", fill: "bg-emerald-500", label: "High Confidence" };
    if (s >= 60) return { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", ring: "stroke-amber-500", fill: "bg-amber-500", label: "Moderate Confidence" };
    return { bg: "bg-red-50", border: "border-red-200", text: "text-red-700", ring: "stroke-red-500", fill: "bg-red-500", label: "Low Confidence" };
  };

  const colors = getScoreColor(score);

  // SVG circular gauge
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  // Claims total for percentage bar
  const grounded = details?.grounded_claims ?? 0;
  const inferred = details?.inferred_claims ?? 0;
  const unsupported = details?.unsupported_claims ?? 0;
  const totalClaims = grounded + inferred + unsupported;

  return (
    <div className={`border-b ${colors.border} ${colors.bg} transition-all duration-300`}>
      {/* Collapsed summary bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-5 py-2.5 hover:brightness-95 transition-all"
      >
        {/* Circular gauge */}
        <div className="relative shrink-0" style={{ width: 40, height: 40 }}>
          <svg width="40" height="40" viewBox="0 0 64 64" className="-rotate-90">
            {/* Background circle */}
            <circle
              cx="32" cy="32" r={radius}
              fill="none"
              stroke="currentColor"
              className="text-black/5"
              strokeWidth="5"
            />
            {/* Score arc */}
            <circle
              cx="32" cy="32" r={radius}
              fill="none"
              className={colors.ring}
              strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className={`text-[11px] font-bold ${colors.text}`}>{score}%</span>
          </div>
        </div>

        {/* Label */}
        <div className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className={`h-3.5 w-3.5 ${colors.text}`} />
            <span className={`text-xs font-semibold ${colors.text}`}>
              {colors.label}
            </span>
          </div>
          {details?.summary && (
            <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
              {details.summary}
            </p>
          )}
        </div>

        {/* Claims mini-bar */}
        {totalClaims > 0 && (
          <div className="hidden sm:flex items-center gap-3 shrink-0">
            <div className="flex items-center gap-1">
              <div className="w-16 h-1.5 rounded-full bg-black/5 overflow-hidden flex">
                <div className="h-full bg-emerald-500 transition-all" style={{ width: `${(grounded / totalClaims) * 100}%` }} />
                <div className="h-full bg-amber-400 transition-all" style={{ width: `${(inferred / totalClaims) * 100}%` }} />
                <div className="h-full bg-red-400 transition-all" style={{ width: `${(unsupported / totalClaims) * 100}%` }} />
              </div>
            </div>
          </div>
        )}

        {/* Expand/collapse */}
        <div className={`shrink-0 ${colors.text}`}>
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </div>
      </button>

      {/* Expanded details */}
      {expanded && details && (
        <div className="px-5 pb-4 pt-1 space-y-3 animate-in slide-in-from-top-1 duration-200">
          {/* Claims breakdown */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-lg bg-white/70 border border-emerald-200/60 p-2.5 text-center">
              <div className="text-lg font-bold text-emerald-700">{grounded}</div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-emerald-600 mt-0.5">
                Grounded
              </div>
              <div className="text-[9px] text-emerald-500 mt-0.5">Direct from docs</div>
            </div>
            <div className="rounded-lg bg-white/70 border border-amber-200/60 p-2.5 text-center">
              <div className="text-lg font-bold text-amber-700">{inferred}</div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-amber-600 mt-0.5">
                Inferred
              </div>
              <div className="text-[9px] text-amber-500 mt-0.5">Reasoned from data</div>
            </div>
            <div className="rounded-lg bg-white/70 border border-red-200/60 p-2.5 text-center">
              <div className="text-lg font-bold text-red-700">{unsupported}</div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-red-600 mt-0.5">
                Unsupported
              </div>
              <div className="text-[9px] text-red-500 mt-0.5">No doc evidence</div>
            </div>
          </div>

          {/* Full-width claims bar */}
          {totalClaims > 0 && (
            <div>
              <div className="flex justify-between text-[9px] text-muted-foreground mb-1">
                <span>Claims Distribution</span>
                <span>{totalClaims} total claims</span>
              </div>
              <div className="h-2.5 rounded-full bg-black/5 overflow-hidden flex">
                <div
                  className="h-full bg-emerald-500 transition-all duration-500"
                  style={{ width: `${(grounded / totalClaims) * 100}%` }}
                  title={`${grounded} grounded claims`}
                />
                <div
                  className="h-full bg-amber-400 transition-all duration-500"
                  style={{ width: `${(inferred / totalClaims) * 100}%` }}
                  title={`${inferred} inferred claims`}
                />
                <div
                  className="h-full bg-red-400 transition-all duration-500"
                  style={{ width: `${(unsupported / totalClaims) * 100}%` }}
                  title={`${unsupported} unsupported claims`}
                />
              </div>
              <div className="flex justify-between mt-1">
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span className="text-[9px] text-muted-foreground">Grounded ({Math.round((grounded / totalClaims) * 100)}%)</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-[9px] text-muted-foreground">Inferred ({Math.round((inferred / totalClaims) * 100)}%)</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-red-400" />
                  <span className="text-[9px] text-muted-foreground">Unsupported ({Math.round((unsupported / totalClaims) * 100)}%)</span>
                </div>
              </div>
            </div>
          )}

          {/* Evaluator summary */}
          {details.summary && (
            <div className="rounded-md bg-white/60 border border-black/5 p-3">
              <div className="flex items-start gap-2">
                <Info className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  {details.summary}
                </p>
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <p className="text-[9px] text-muted-foreground/60 italic text-center">
            Accuracy is an AI self-assessment and may not reflect ground truth. Always verify critical data points.
          </p>
        </div>
      )}
    </div>
  );
}

import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Legend
} from "recharts";

/* ── Markdown Renderer Component ───────────────────────────────── */

// Helper to extract plain text from React children
function extractText(node: any): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!node) return "";
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (node.props && node.props.children) return extractText(node.props.children);
  return "";
}

function CustomTable({ children, primaryColor, secondaryColor, ...props }: any) {
  const [viewMode, setViewMode] = useState<"table" | "chart">("table");

  // Parse the table data from the React children
  const parseTable = () => {
    try {
      const headers: string[] = [];
      const rows: any[] = [];
      
      const childrenArray = React.Children.toArray(children);
      const thead: any = childrenArray.find((c: any) => c.type === "thead");
      const tbody: any = childrenArray.find((c: any) => c.type === "tbody");

      if (thead) {
        const tr = React.Children.toArray(thead.props.children)[0] as any;
        if (tr && tr.props.children) {
          React.Children.forEach(tr.props.children, (th: any) => {
            headers.push(extractText(th).trim());
          });
        }
      }

      if (tbody) {
        React.Children.forEach(tbody.props.children, (tr: any) => {
          if (tr.type !== "tr") return;
          const rowData: any = {};
          React.Children.forEach(tr.props.children, (td: any, idx: number) => {
            const valStr = extractText(td).trim();
            // Try to parse as number
            const numVal = Number(valStr.replace(/[^0-9.-]+/g, ""));
            const header = headers[idx] || `Col${idx}`;
            rowData[header] = !isNaN(numVal) && valStr.match(/[0-9]/) ? numVal : valStr;
          });
          rows.push(rowData);
        });
      }

      return { headers, rows };
    } catch (err) {
      console.error("Failed to parse table", err);
      return { headers: [], rows: [] };
    }
  };

  const { headers, rows } = parseTable();

  // Heuristic for numeric table: must have >1 columns, and at least some rows where column 2+ is a number
  const isNumeric = headers.length > 1 && rows.some(r => typeof r[headers[1]] === "number");

  if (!isNumeric) {
    return (
      <div className="my-6 overflow-x-auto rounded-md border">
        <table className="w-full text-left text-sm" {...props}>{children}</table>
      </div>
    );
  }

  const yKeys = headers.slice(1);
  const xKey = headers[0];
  const colors = [primaryColor || "#0f172a", secondaryColor || "#334155", "#64748b", "#94a3b8", "#cbd5e1"];

  return (
    <div className="my-6 rounded-md border bg-card text-card-foreground shadow-sm overflow-hidden">
      <div className="flex items-center justify-between border-b px-4 py-2 bg-muted/30">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {viewMode === "table" ? "Data Table" : "Chart View"}
        </div>
        <div className="flex bg-muted rounded-md p-0.5">
          <button
            onClick={() => setViewMode("table")}
            className={`flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium transition-colors ${viewMode === "table" ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
          >
            <TableIcon className="h-3.5 w-3.5" /> Table
          </button>
          <button
            onClick={() => setViewMode("chart")}
            className={`flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium transition-colors ${viewMode === "chart" ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
          >
            <BarChart3 className="h-3.5 w-3.5" /> Chart
          </button>
        </div>
      </div>

      <div className="p-4">
        {viewMode === "table" ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" {...props}>{children}</table>
          </div>
        ) : (
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis dataKey={xKey} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#6b7280" }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#6b7280" }} dx={-10} />
                <RechartsTooltip 
                  contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }}
                  cursor={{ fill: "#f3f4f6" }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />
                {yKeys.map((key, i) => (
                  <Bar key={key} dataKey={key} fill={colors[i % colors.length]} radius={[4, 4, 0, 0]} maxBarSize={50} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}


function MarkdownRenderer({ content, primaryColor, secondaryColor }: { content: string, primaryColor?: string, secondaryColor?: string }) {
  // Lazy import react-markdown
  const [ReactMarkdown, setReactMarkdown] = useState<any>(null);
  const [remarkGfm, setRemarkGfm] = useState<any>(null);

  useEffect(() => {
    Promise.all([
      import("react-markdown"),
      import("remark-gfm"),
    ]).then(([md, gfm]) => {
      setReactMarkdown(() => md.default);
      setRemarkGfm(() => gfm.default);
    });
  }, []);

  if (!ReactMarkdown) {
    // Fallback: show pre-formatted text while markdown loads
    return <div className="whitespace-pre-wrap text-sm leading-relaxed">{content}</div>;
  }

  return (
    <ReactMarkdown 
      remarkPlugins={remarkGfm ? [remarkGfm] : []}
      components={{
        table: (props: any) => <CustomTable {...props} primaryColor={primaryColor} secondaryColor={secondaryColor} />
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

/* ── Versions Tab ───────────────────────────────────────────── */

function VersionsTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const ready = deal.sections.filter(s => !s.optional && s.state === "ready").length;
  const total = deal.sections.filter(s => !s.optional).length;
  const pending = deal.sections.filter(s => !s.optional && s.state === "pending");

  const submit = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await api.versions.submit(deal.id, notes);
      setNotes("");
      refresh();
    } catch (err) {
      console.error("Submit failed:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const approve = async (versionId: string) => {
    try {
      await api.versions.approve(deal.id, versionId);
      refresh();
    } catch (err) {
      console.error("Approve failed:", err);
    }
  };

  return (
    <div className="space-y-4">
      <div className="doc-card">
        <div className="doc-section-header"><span>Validation Summary</span></div>
        <div className="p-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <div className="text-sm">Mandatory sections ready <span className="ml-2 font-mono text-muted-foreground">{ready}/{total}</span></div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary" style={{ width: `${total > 0 ? (ready / total) * 100 : 0}%` }} />
              </div>
            </div>
            <div>
              <div className="text-sm">Approved version</div>
              <div className={`mt-1 inline-block rounded-full px-3 py-0.5 text-xs font-semibold ${
                deal.versions.some(v => v.status === "approved")
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-muted text-muted-foreground"
              }`}>{deal.versions.some(v => v.status === "approved") ? "Yes" : "No"}</div>
            </div>
            <div>
              <div className="text-sm">Total versions</div>
              <div className="mt-1 inline-block rounded-full bg-muted px-3 py-0.5 text-xs font-semibold text-muted-foreground">{deal.versions.length}</div>
            </div>
          </div>
          {pending.length > 0 && (
            <div className="mt-4 rounded-md border bg-surface p-3">
              <div className="text-xs font-semibold text-muted-foreground">Pending mandatory sections:</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {pending.map(s => (
                  <span key={s.id} className="rounded-full border border-warning/40 bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning-foreground">{s.title}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="doc-card">
        <div className="doc-section-header"><span>Submit for Review</span></div>
        <div className="space-y-3 p-4">
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3} placeholder="Reviewer notes (optional)" className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          <button
            onClick={submit}
            disabled={submitting}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
            {submitting ? "Submitting…" : "Submit version for review"}
          </button>
        </div>
      </div>

      <div className="doc-card">
        <div className="doc-section-header"><Clock className="h-4 w-4 shrink-0" /><span>Versions ({deal.versions.length})</span></div>
        {deal.versions.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">No versions yet. Submit the draft for review above.</div>
        ) : (
          <ul className="divide-y">
            {deal.versions.map(v => (
              <li key={v.id} className="flex items-center justify-between p-4 text-sm">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{v.id}</span>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                      v.status === "approved" ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "border-border bg-muted text-muted-foreground"
                    }`}>{v.status}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">{v.notes || "—"}</div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-xs text-muted-foreground">{new Date(v.created_at).toLocaleString()}</div>
                  {v.status === "submitted" && (
                    <button
                      onClick={() => approve(v.id)}
                      className="inline-flex h-7 items-center gap-1 rounded-md bg-emerald-600 px-2 text-xs font-medium text-white hover:bg-emerald-700"
                    >
                      <CheckCircle2 className="h-3 w-3" /> Approve
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="doc-card">
        <div className="doc-section-header"><span>Audit Trail ({deal.audit_entries.length})</span></div>
        <ul className="divide-y">
          {deal.audit_entries.slice().reverse().map(a => (
            <li key={a.id} className="flex items-start justify-between gap-4 p-4">
              <div>
                <div className="font-semibold">{a.action}</div>
                <div className="text-xs text-muted-foreground">{a.subject}</div>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                <div className="font-medium text-foreground">{a.user}</div>
                <div>{new Date(a.created_at).toLocaleString()}</div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* ── Export Tab ──────────────────────────────────────────────── */

function ExportTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const ready = deal.sections.filter(s => !s.optional && s.state === "ready").length;
  const total = deal.sections.filter(s => !s.optional).length;
  const pending = total - ready;
  const [exporting, setExporting] = useState<string | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);

  const handleExport = async (format: string) => {
    setExporting(format);
    try {
      await api.exports.download(deal.id, format);
      refresh();
    } catch (err) {
      console.error(`Export ${format} failed:`, err);
    } finally {
      setExporting(null);
    }
  };

  const handleGenerateReport = async () => {
    setGeneratingReport(true);
    try {
      await api.exports.generateReport(deal.id);
      refresh();
    } catch (err) {
      console.error("Report generation failed:", err);
    } finally {
      setGeneratingReport(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Generate Combined Report */}
      <div className="doc-card">
        <div className="doc-section-header"><BookOpenCheck className="h-4 w-4 shrink-0" /><span>Generate Combined Report</span></div>
        <div className="p-5">
          <p className="text-sm text-muted-foreground mb-4">
            Generate a comprehensive PDF report combining all section narratives into a single credit pitch book document.
          </p>
          <button
            onClick={handleGenerateReport}
            disabled={generatingReport}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-60"
          >
            {generatingReport ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
            {generatingReport ? "Generating report…" : "Generate Report (PDF)"}
          </button>
        </div>
      </div>

      <div className="doc-card">
        <div className="doc-section-header"><Download className="h-4 w-4 shrink-0" /><span>Export Pitch Book</span></div>
        <div className="space-y-4 p-5">
          {(pending > 0 || deal.versions.length === 0) && (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-4">
              <div className="flex items-center gap-2 font-semibold"><TriangleAlert className="h-4 w-4" /> Export blocked</div>
              <ul className="ml-6 mt-2 list-disc text-sm">
                {pending > 0 && <li>{pending} mandatory section(s) not yet marked ready.</li>}
                {deal.versions.length === 0 && <li>No approved version. Submit and approve a version first.</li>}
              </ul>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            {["pptx", "pdf", "docx"].map(fmt => (
              <button
                key={fmt}
                onClick={() => handleExport(fmt)}
                disabled={exporting !== null}
                className="flex items-start gap-3 rounded-md border bg-card p-4 text-left hover:bg-surface disabled:opacity-60"
              >
                {exporting === fmt
                  ? <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  : <FileText className="h-5 w-5 text-muted-foreground" />
                }
                <div>
                  <div className="font-medium">Export as {fmt.toUpperCase()}</div>
                  <div className="text-xs text-muted-foreground">Download pitch book</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
