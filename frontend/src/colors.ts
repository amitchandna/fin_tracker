import { useEffect, useState } from "react";

/** Categorical slots in fixed order (validated palette). Colour follows the
 * entity, never its rank in the current view, so filters never repaint series. */
const SLOT_COUNT = 8;
export const MAX_SERIES = 7; // the 8th visible series is always "Other"

function readSlots(): { series: string[]; other: string } {
  const style = getComputedStyle(document.documentElement);
  const series = Array.from({ length: SLOT_COUNT }, (_, i) => style.getPropertyValue(`--series-${i + 1}`).trim());
  return { series, other: style.getPropertyValue("--series-other").trim() };
}

/** Re-reads the palette when the colour scheme changes. */
export function usePalette() {
  const [palette, setPalette] = useState(readSlots);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setPalette(readSlots());
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return palette;
}

/** Map a stable list of entity keys to colours; anything past MAX_SERIES is "Other". */
export function colorMap(order: string[], palette: { series: string[]; other: string }) {
  const map = new Map<string, string>();
  order.slice(0, MAX_SERIES).forEach((key, i) => map.set(key, palette.series[i]));
  return (key: string) => map.get(key) ?? palette.other;
}

export const PAYMENT_METHOD_ORDER = ["credit", "debit", "transfer", "check", "cash"];
