import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number, decimals = 2) {
  if (!+bytes) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
];

/**
 * Formats a calendar date-only string (YYYY-MM-DD) into human-readable format (e.g. 17 May 2004)
 * with strict date-only semantics, completely avoiding JavaScript UTC/local timezone shifts.
 */
export function formatDateOnly(dateStr?: string | null): string {
  if (!dateStr) return "Not specified";
  const clean = dateStr.split("T")[0].trim();
  const parts = clean.split("-");
  if (parts.length === 3) {
    const year = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    if (!isNaN(year) && !isNaN(month) && !isNaN(day) && month >= 1 && month <= 12) {
      return `${String(day).padStart(2, "0")} ${MONTH_NAMES[month - 1]} ${year}`;
    }
  }
  return clean;
}
