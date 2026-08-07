import { createFileRoute, useRouter } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { ArrowLeft, FilePlus2, Loader2 } from "lucide-react";
import { api, type DealType } from "@/lib/deals";
import { CurrencyCombobox } from "@/components/CurrencyCombobox";
import { CompanyCombobox, type CompanyInfo } from "@/components/CompanyCombobox";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/deals/new")({
  head: () => ({ meta: [{ title: "New Deal — Credit Pitch Book" }] }),
  component: NewDeal,
});

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}{required && <span className="ml-0.5 text-destructive">*</span>}
      </label>
      {children}
    </div>
  );
}

const inputCls = "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const selectCls = "flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function NewDeal() {
  const { user } = useAuth();
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    customer: "", customerType: "Existing" as DealType, industry: "", segment: "",
    geography: "", kyc: "verified" as "verified" | "pending",
    facility: "Term Loan", currency: "INR", amount: 0, tenure: 12,
    pricing: "", repayment: "Equated quarterly", collateral: true, due: "",
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm(p => ({ ...p, [k]: v }));

  if (user?.role !== "relationship_manager") {
    return (
      <main className="mx-auto max-w-2xl px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">Deal creation is restricted</h1>
        <p className="mt-2 text-sm text-muted-foreground">Only Relationship Managers can create a new deal.</p>
        <Link to="/" className="mt-5 inline-flex rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">Return to Dashboard</Link>
      </main>
    );
  }

  const handleCompanySelect = async (company: CompanyInfo | null) => {
    if (company) {
      set("customer", company.name);
      try {
        const details = await api.companies.details(company.name);
        if (details) {
          if (details.industry) set("industry", details.industry);
          if (details.segment) set("segment", details.segment);
          if (details.geography) set("geography", details.geography);
          if (details.kyc_status) {
            set("kyc", details.kyc_status.toLowerCase() === "verified" ? "verified" : "pending");
          }
        }
      } catch (e) {
        console.error("Failed to fetch company details", e);
      }
      
      // Defaults for fields not returned by MCP
      set("pricing", "Repo + 285 bps");
      set("amount", 100000000);
      set("tenure", 60);
      set("due", new Date(new Date().setMonth(new Date().getMonth() + 1)).toISOString().split('T')[0]);
    } else {
      set("customer", "");
    }
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.customer.trim() || submitting) return;
    setSubmitting(true);
    try {
      const deal = await api.deals.create({
        customer: form.customer.trim(),
        customer_type: form.customerType,
        industry: form.industry,
        segment: form.segment,
        geography: form.geography,
        kyc: form.kyc,
        facility: form.facility,
        currency: form.currency,
        amount: Number(form.amount),
        tenure: Number(form.tenure),
        pricing: form.pricing,
        repayment: form.repayment,
        collateral: form.collateral,
        due: form.due,
      });
      router.navigate({ to: "/deals/$dealId", params: { dealId: deal.id } });
    } catch (err) {
      console.error("Failed to create deal:", err);
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
      <div className="mb-4">
        <Link to="/" className="inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-medium hover:bg-accent hover:text-accent-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
        </Link>
      </div>
      <form onSubmit={submit} className="mx-auto max-w-3xl">
        <div className="doc-card mb-4">
          <div className="doc-section-header"><FilePlus2 className="h-4 w-4 shrink-0" /><span>Customer Details</span></div>
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <Field label="Legal name" required>
              <CompanyCombobox value={form.customer} onChange={handleCompanySelect} />
            </Field>
            <Field label="Customer type">
              <select className={selectCls} value={form.customerType} onChange={e => set("customerType", e.target.value as DealType)}>
                <option value="Existing">Existing</option>
                <option value="New-to-bank">New-to-bank</option>
              </select>
            </Field>
            <Field label="Industry"><input className={inputCls} value={form.industry} onChange={e => set("industry", e.target.value)} /></Field>
            <Field label="Segment">
              <select className={selectCls} value={form.segment} onChange={e => set("segment", e.target.value)}>
                <option>SME</option><option>Mid Corporate</option><option>Large Corporate</option>
              </select>
            </Field>
            <Field label="Geography"><input className={inputCls} value={form.geography} onChange={e => set("geography", e.target.value)} /></Field>
            <Field label="KYC status">
              <select className={selectCls} value={form.kyc} onChange={e => set("kyc", e.target.value as "verified" | "pending")}>
                <option value="verified">Verified</option><option value="pending">Pending</option>
              </select>
            </Field>
          </div>
        </div>

        <div className="doc-card mb-4">
          <div className="doc-section-header"><span>Facility Details</span></div>
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <Field label="Product / facility type">
              <select className={selectCls} value={form.facility} onChange={e => set("facility", e.target.value)}>
                <option>Term Loan</option><option>Working Capital</option><option>Syndicated Loan</option>
              </select>
            </Field>
            <Field label="Currency">
              <CurrencyCombobox value={form.currency} onChange={(code) => set("currency", code)} />
            </Field>
            <Field label="Amount (in units of currency)"><input type="number" min={0} className={inputCls} value={form.amount} onChange={e => set("amount", Number(e.target.value))} /></Field>
            <Field label="Tenure (months)"><input type="number" min={1} className={inputCls} value={form.tenure} onChange={e => set("tenure", Number(e.target.value))} /></Field>
            <Field label="Pricing"><input className={inputCls} value={form.pricing} onChange={e => set("pricing", e.target.value)} /></Field>
            <Field label="Repayment"><input className={inputCls} value={form.repayment} onChange={e => set("repayment", e.target.value)} /></Field>
            <Field label="Collateral required">
              <select className={selectCls} value={String(form.collateral)} onChange={e => set("collateral", e.target.value === "true")}>
                <option value="true">Yes</option><option value="false">No (Clean)</option>
              </select>
            </Field>
            <Field label="Target completion date"><input type="date" className={inputCls} value={form.due} onChange={e => set("due", e.target.value)} /></Field>
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <Link to="/" className="inline-flex h-9 items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground">Cancel</Link>
          <button type="submit" disabled={submitting} className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-60">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePlus2 className="h-4 w-4" />}
            {submitting ? "Creating…" : "Create deal"}
          </button>
        </div>
      </form>
    </main>
  );
}
