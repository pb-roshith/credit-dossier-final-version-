import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import {
  Plus, Briefcase, Clock, TriangleAlert, CircleCheck, FileText, Search, ArrowRight, Loader2,
} from "lucide-react";
import { api, formatAmount, type Status, type DealType, type DealListItem } from "@/lib/deals";

export const Route = createFileRoute("/")(  {
  head: () => ({
    meta: [
      { title: "Credit Pitch Book Pipeline" },
      { name: "description", content: "Initiate, draft, review, and export pitch books with full traceability." },
    ],
  }),
  component: Dashboard,
});

function StatusBadge({ status }: { status: Status }) {
  const cls =
    status === "In Progress" ? "bg-info/12 text-info border-info/30"
    : status === "In Review" ? "bg-warning/15 text-warning-foreground border-warning/40"
    : status === "Draft" ? "bg-muted text-muted-foreground border-border"
    : "bg-primary/10 text-primary border-primary/25";
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>{status}</span>;
}

function TypeBadge({ type }: { type: DealType }) {
  const cls = type === "Existing" ? "bg-primary/10 text-primary border-primary/25" : "bg-info/12 text-info border-info/30";
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>{type}</span>;
}

function Dashboard() {
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [deals, setDeals] = useState<DealListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const statusParam = statusFilter !== "all"
      ? statusFilter.replace("_", " ").replace(/\b\w/g, l => l.toUpperCase())
      : undefined;

    api.deals.list({ status: statusParam, search: q || undefined })
      .then(data => { if (!cancelled) setDeals(data); })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [q, statusFilter]);

  const all = deals;
  const kpis = [
    { label: "Total deals", value: String(all.length), Icon: Briefcase },
    { label: "Active drafts", value: String(all.filter(d => d.status === "Draft" || d.status === "In Progress").length), Icon: Clock },
    { label: "In review", value: String(all.filter(d => d.status === "In Review").length), Icon: TriangleAlert },
    { label: "Approved/Exported", value: String(all.filter(d => d.status === "Approved" || d.status === "Exported").length), Icon: CircleCheck },
  ];

  return (
    <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Credit Pitch Book Pipeline</h1>
          <p className="text-sm text-muted-foreground">Initiate, draft, review, and export pitch books with full traceability.</p>
        </div>
        <Link to="/deals/new" className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90">
          <Plus className="h-4 w-4" /> New Deal
        </Link>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {kpis.map(({ label, value, Icon }) => (
          <div key={label} className="kpi-card">
            <div className="flex items-start justify-between">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
              <Icon className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-2 text-2xl font-bold tabular-nums">{value}</div>
          </div>
        ))}
      </div>

      <div className="doc-card">
        <div className="doc-section-header justify-between">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="h-4 w-4 shrink-0" />
            <span className="truncate">Deal Pipeline</span>
          </div>
          <div className="hidden items-center gap-2 sm:flex">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-primary-foreground/70" />
              <input
                value={q} onChange={e => setQ(e.target.value)}
                className="h-7 w-44 rounded-md border border-primary-foreground/30 bg-primary-foreground/10 pl-7 pr-2 text-xs text-primary-foreground placeholder:text-primary-foreground/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Search…"
              />
            </div>
            <select
              value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="h-7 rounded-md border border-primary-foreground/30 bg-primary-foreground/10 px-2 text-xs font-medium text-primary-foreground"
            >
              <option value="all" className="text-foreground">All statuses</option>
              <option value="Draft" className="text-foreground">Draft</option>
              <option value="In Progress" className="text-foreground">In Progress</option>
              <option value="In Review" className="text-foreground">In Review</option>
              <option value="Approved" className="text-foreground">Approved</option>
              <option value="Exported" className="text-foreground">Exported</option>
            </select>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading deals…
          </div>
        )}

        {error && (
          <div className="px-4 py-8 text-center text-sm text-destructive">
            Failed to load deals: {error}
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="hidden sm:block">
              <table className="doc-table">
                <thead>
                  <tr>
                    <th>Customer</th><th>Type</th><th>Facility</th><th className="text-right">Amount</th>
                    <th>Due</th><th>Status</th><th>Progress</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {deals.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <div className="font-semibold">{d.customer}</div>
                        <div className="text-xs text-muted-foreground">{d.sector} · {d.city}</div>
                      </td>
                      <td><TypeBadge type={d.customer_type} /></td>
                      <td className="text-sm">{d.facility}</td>
                      <td className="text-right font-mono text-sm">{formatAmount(d.amount, d.currency)}</td>
                      <td className="text-sm">{d.due}</td>
                      <td><StatusBadge status={d.status} /></td>
                      <td className="w-40">
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${d.sections_total > 0 ? (d.sections_ready / d.sections_total) * 100 : 0}%` }} />
                        </div>
                        <div className="mt-1 text-[11px] text-muted-foreground">{d.sections_ready}/{d.sections_total} sections</div>
                      </td>
                      <td>
                        <Link to="/deals/$dealId" params={{ dealId: d.id }} className="inline-flex h-8 items-center justify-center gap-2 rounded-md px-3 text-xs font-medium hover:bg-accent hover:text-accent-foreground">
                          Open <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {deals.length === 0 && (
                    <tr><td colSpan={8} className="py-10 text-center text-sm text-muted-foreground">No deals match your filters.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <ul className="divide-y sm:hidden">
              {deals.map((d) => (
                <li key={d.id}>
                  <Link to="/deals/$dealId" params={{ dealId: d.id }} className="block p-3 active:bg-surface">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate font-semibold">{d.customer}</div>
                        <div className="truncate text-xs text-muted-foreground">{d.sector}</div>
                      </div>
                      <StatusBadge status={d.status} />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{d.facility}</span>
                      <span className="font-mono">{formatAmount(d.amount, d.currency)}</span>
                    </div>
                    <div className="mt-2">
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${d.sections_total > 0 ? (d.sections_ready / d.sections_total) * 100 : 0}%` }} />
                      </div>
                      <div className="mt-1 text-[11px] text-muted-foreground">{d.sections_ready}/{d.sections_total} mandatory sections · due {d.due}</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </main>
  );
}
