import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatEval(cp: number | null | undefined, mateIn?: number | null): string {
  if (mateIn != null) return `#${mateIn > 0 ? mateIn : mateIn}`;
  if (cp == null) return "—";
  const sign = cp >= 0 ? "+" : "";
  return `${sign}${(cp / 100).toFixed(2)}`;
}
