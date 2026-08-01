import { Link, useRouterState } from "@tanstack/react-router";
import { BookOpen, Factory, LayoutDashboard, FilePlus2 } from "lucide-react";

export function AppHeader() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const isDashboard = pathname === "/" || pathname === "/dashboard";
  const isNew = pathname.startsWith("/deals/new");
  const isManufacture = pathname.startsWith("/manufacture-data");

  const tabCls = (active: boolean) =>
    `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
      active ? "bg-primary-foreground/15" : "hover:bg-primary-foreground/10"
    }`;

  return (
    <header className="border-b bg-primary text-primary-foreground">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 px-3 py-2 sm:px-6">
        <div className="flex items-center gap-1">
          <Link to="/" className="flex items-center gap-2 rounded-md px-3 py-2 font-semibold">
            <BookOpen className="h-5 w-5" />
            <span>Credit Pitch Book</span>
          </Link>
          <Link to="/" className={tabCls(isDashboard)}>
            <LayoutDashboard className="h-4 w-4" /> Dashboard
          </Link>
          <Link to="/deals/new" className={tabCls(isNew)}>
            <FilePlus2 className="h-4 w-4" /> New Deal
          </Link>
          <Link to="/manufacture-data" className={tabCls(isManufacture)}>
            <Factory className="h-4 w-4" /> Manufacture Data
          </Link>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right text-xs leading-tight">
            <div className="font-semibold">Credit Dossier</div>
            <div className="opacity-75">Pipeline v1.0</div>
          </div>
        </div>
      </div>
    </header>
  );
}
