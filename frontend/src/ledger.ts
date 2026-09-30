import type { LedgerKind } from "./types";

export const KIND_LABELS: Record<LedgerKind, string> = {
  invoice: "Накладная",
  sale: "Касса",
  write_off: "Списание",
  stocktake: "Переучёт",
  revaluation: "Переоценка",
};
