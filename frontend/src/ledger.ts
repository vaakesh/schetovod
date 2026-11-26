import type { LedgerEntry, LedgerKind, LedgerSort } from "./types";

const SORT_KEY = "ledger-sort";

export function savedLedgerSort(): LedgerSort {
  try {
    return window.localStorage.getItem(SORT_KEY) === "kind" ? "kind" : "number";
  } catch {
    return "number";
  }
}

export function saveLedgerSort(value: LedgerSort) {
  try {
    window.localStorage.setItem(SORT_KEY, value);
  } catch {
    // the current session still shares the selection between both pages
  }
}

// the till operations, they never touch the stock
export const CASH_KINDS: LedgerKind[] = ["cash_in", "cash_out", "cash_count"];

export function touchesStock(entry: LedgerEntry): boolean {
  return !CASH_KINDS.includes(entry.kind);
}

// a cashless sale leaves the till as it was
export function touchesCash(entry: LedgerEntry): boolean {
  return CASH_KINDS.includes(entry.kind) || Number(entry.cash) !== 0;
}

export const KIND_LABELS: Record<LedgerKind, string> = {
  invoice: "Накладная",
  sale: "Продажа",
  write_off: "Списание",
  stock_in: "Приход товара",
  stocktake: "Переучёт",
  revaluation: "Переоценка",
  cash_in: "Внесение",
  cash_out: "Выдача",
  cash_count: "Сверка кассы",
};
