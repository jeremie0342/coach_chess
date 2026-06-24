import { cn } from "@/lib/utils";

export function EvalBar({
  cp,
  mate,
  orientation = "white",
  height,
  className,
}: {
  cp?: number | null;
  mate?: number | null;
  orientation?: "white" | "black";
  height?: number | string;
  className?: string;
}) {
  let pct = 50;
  let label = "0.0";
  if (mate != null) {
    pct = mate > 0 ? 100 : 0;
    label = `#${Math.abs(mate)}`;
  } else if (cp != null) {
    const clamped = Math.max(-800, Math.min(800, cp));
    pct = 50 + (clamped / 800) * 50;
    label = `${cp >= 0 ? "+" : ""}${(cp / 100).toFixed(2)}`;
  }
  const whitePct = orientation === "white" ? pct : 100 - pct;

  return (
    <div
      className={cn(
        "w-5 rounded-md overflow-hidden bg-black border border-[var(--border)] relative font-mono text-[10px]",
        className,
      )}
      style={height != null ? { height } : undefined}
      title={label}
    >
      <div
        className="absolute inset-x-0 bottom-0 bg-white"
        style={{ height: `${whitePct}%`, transition: "height 400ms cubic-bezier(0.22, 1, 0.36, 1)" }}
      />
      <div className={cn("absolute inset-x-0 text-center", whitePct > 50 ? "bottom-1 text-black" : "top-1 text-white")}>
        {label}
      </div>
    </div>
  );
}
