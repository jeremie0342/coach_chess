"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  href: string;
  filename?: string;
  label: React.ReactNode;
  className?: string;
  disabled?: boolean;
  title?: string;
  icon?: React.ReactNode;
};

/**
 * Async download button: fetches the URL as a blob, then triggers a real
 * download via a temporary anchor. Disables itself and shows a spinner
 * while the request is in flight — prevents repeat clicks on slow exports
 * like MP4 (the browser has no way to tell us when a plain <a download>
 * finishes, so we drive it ourselves).
 */
export function DownloadButton({
  href, filename, label, className, disabled, title, icon,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onClick = async () => {
    if (loading || disabled) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(href, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();

      // Derive filename from Content-Disposition if backend set it, else use prop
      let name = filename ?? "download";
      const cd = res.headers.get("Content-Disposition");
      if (cd) {
        const m = cd.match(/filename="([^"]+)"|filename=([^;]+)/);
        if (m) name = (m[1] ?? m[2]).trim();
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      title={error ?? title}
      className={cn(
        "inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed",
        className,
      )}
    >
      {loading
        ? <Loader2 className="size-3.5 animate-spin" />
        : (icon ?? <Download className="size-3.5" />)
      }
      {label}
    </button>
  );
}
