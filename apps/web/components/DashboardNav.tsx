const DASHBOARD_LINKS = [
  { href: "/", label: "Audit" },
  { href: "/codex", label: "Codex" },
  { href: "/debug", label: "Debug" },
];

interface DashboardNavProps {
  active: "audit" | "codex" | "debug";
  variant?: "light" | "dark";
}

export function DashboardNav({ active, variant = "light" }: DashboardNavProps) {
  const dark = variant === "dark";
  return (
    <nav
      aria-label="Dashboard views"
      className={`mx-auto mb-6 flex max-w-7xl flex-wrap items-center gap-3 rounded-2xl border p-3 text-sm ${
        dark
          ? "border-slate-700 bg-slate-950/80 text-slate-200"
          : "border-slate-300 bg-white text-slate-900"
      }`}
    >
      <span className={dark ? "font-bold text-cyan-200" : "font-bold"}>
        Dashboards
      </span>
      <div className="flex flex-wrap gap-2">
        {DASHBOARD_LINKS.map((link) => {
          const isActive = link.href === `/${active === "audit" ? "" : active}`;
          return (
            <a
              key={link.href}
              href={link.href}
              aria-current={isActive ? "page" : undefined}
              className={`rounded-xl px-3 py-2 font-bold transition ${
                isActive
                  ? dark
                    ? "bg-cyan-300 text-slate-950"
                    : "bg-slate-900 text-white"
                  : dark
                    ? "border border-slate-700 text-slate-200 hover:border-cyan-300"
                    : "border border-slate-300 text-slate-900 hover:border-slate-900"
              }`}
            >
              {link.label}
            </a>
          );
        })}
      </div>
    </nav>
  );
}
