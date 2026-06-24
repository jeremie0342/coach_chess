"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Home,
  CalendarDays,
  Target,
  Puzzle,
  Swords,
  BookOpen,
  LineChart,
  Search,
  FileText,
  Settings,
  Bell,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/lib/ui-store";
import { useIdentity } from "@/hooks/useIdentity";

const NAV = [
  { group: "Coach", items: [
    { href: "/", label: "Dashboard", icon: Home },
    { href: "/roadmap", label: "Roadmap 2000", icon: Target },
    { href: "/today", label: "Plan du jour", icon: CalendarDays },
    { href: "/weaknesses", label: "Faiblesses", icon: Target },
    { href: "/progress", label: "Progression", icon: LineChart },
  ]},
  { group: "Entraînement", items: [
    { href: "/puzzles", label: "Puzzles", icon: Puzzle },
    { href: "/repertoire", label: "Répertoire SR", icon: BookOpen },
    { href: "/opening-trainer", label: "Opening trainer", icon: BookOpen },
    { href: "/opening-trainer/repertoire", label: "Mon répertoire", icon: BookOpen },
    { href: "/play", label: "Jouer vs Stockfish", icon: Swords },
    { href: "/lab-positions", label: "Rejouer mes blunders", icon: Swords },
  ]},
  { group: "Analyse", items: [
    { href: "/games", label: "Mes parties", icon: FileText },
    { href: "/lab", label: "Lab d'analyse", icon: FileText },
    { href: "/live-debrief", label: "Live debrief", icon: FileText },
    { href: "/scout", label: "Scout adversaire", icon: Search },
  ]},
  { group: "Outils", items: [
    { href: "/explorer", label: "Explorer", icon: BookOpen },
    { href: "/repertoire-lines", label: "Lignes répertoire", icon: BookOpen },
    { href: "/similar", label: "Positions similaires", icon: Search },
    { href: "/tablebase", label: "Tablebase", icon: BookOpen },
    { href: "/weekly", label: "Rapports hebdo", icon: FileText },
    { href: "/extras", label: "Extras (cards, OCR…)", icon: Settings },
    { href: "/notifications", label: "Notifications", icon: Bell },
    { href: "/admin", label: "Admin / Pipeline", icon: Settings },
  ]},
];

function NavList({ path, onItemClick }: { path: string; onItemClick?: () => void }) {
  const me = useIdentity();
  return (
    <>
      <div className="px-3 mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Coach</div>
        <div className="text-lg font-semibold">{me.display_name}</div>
        {me.lichess_username && (
          <div className="text-[10px] text-[var(--muted)] mt-0.5 font-mono">
            chess.com · lichess
          </div>
        )}
      </div>
      <nav className="space-y-5">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="px-3 mb-2 text-[10px] uppercase tracking-widest text-[var(--muted)]">
              {g.group}
            </div>
            <ul className="space-y-0.5">
              {g.items.map((it) => {
                const active = path === it.href;
                const Icon = it.icon;
                return (
                  <li key={it.href}>
                    <Link
                      href={it.href}
                      onClick={onItemClick}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm",
                        active
                          ? "bg-[var(--surface-2)] text-[var(--foreground)]"
                          : "text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)]/60",
                      )}
                    >
                      <Icon className="size-4" />
                      <span>{it.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </>
  );
}

export function Sidebar() {
  const path = usePathname();
  const { isSidebarOpen, closeSidebar } = useUIStore();

  // Close drawer on route change
  useEffect(() => { closeSidebar(); }, [path, closeSidebar]);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeSidebar(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeSidebar]);

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:block w-64 shrink-0 border-r bg-[var(--surface)] px-3 py-5 sticky top-0 h-screen overflow-y-auto">
        <NavList path={path} />
      </aside>

      {/* Mobile drawer */}
      <AnimatePresence>
        {isSidebarOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="md:hidden fixed inset-0 z-40 bg-black/60"
              onClick={closeSidebar}
            />
            <motion.aside
              key="drawer"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="md:hidden fixed inset-y-0 left-0 z-50 w-72 bg-[var(--surface)] border-r border-[var(--border)] px-3 py-5 overflow-y-auto"
            >
              <button
                onClick={closeSidebar}
                aria-label="Fermer"
                className="absolute top-3 right-3 p-2 rounded hover:bg-[var(--surface-2)]"
              >
                <X className="size-4" />
              </button>
              <NavList path={path} onItemClick={closeSidebar} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
