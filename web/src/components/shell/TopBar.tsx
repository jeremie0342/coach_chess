"use client";

import { Menu } from "lucide-react";
import { useUIStore } from "@/lib/ui-store";
import { useIdentity } from "@/hooks/useIdentity";

export function TopBar() {
  const toggle = useUIStore((s) => s.toggleSidebar);
  const me = useIdentity();
  return (
    <header className="md:hidden sticky top-0 z-30 flex items-center gap-3 px-4 h-12 bg-[var(--surface)] border-b border-[var(--border)]">
      <button
        onClick={toggle}
        aria-label="Ouvrir le menu"
        className="p-2 -ml-2 rounded hover:bg-[var(--surface-2)]"
      >
        <Menu className="size-5" />
      </button>
      <div className="text-sm font-semibold">Coach <span className="text-[var(--muted)]">· {me.display_name}</span></div>
    </header>
  );
}
