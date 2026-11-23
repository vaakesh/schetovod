import { request } from "./api";
import { formatMoney, formatNumber, formatQuantityFromAmount, plural } from "./format";

export type Unit = "шт" | "кг";

export interface LineFields {
  name: string;
  unit: Unit;
  price: string;
  quantity: string;
  byAmount: boolean;
  enteredAmount: string;
}

export interface CountLine {
  id: number;
  name: string;
  unit: Unit;
  price: string | null;
  quantity: string | null;
  amount: string;
  version: number;
}

export interface CountSummary {
  id: number;
  started_at: string;
  completed_at: string | null;
  version: number;
  line_count: number;
  total: string;
}

export interface CountDocument extends CountSummary {
  lines: CountLine[];
}

export interface Suggestion {
  name: string;
  unit: Unit;
  price: string | null;
  current_line_id: number | null;
  current_quantity: string | null;
  current_amount: string | null;
}

export interface CountDraft extends LineFields {
  requestId: string;
  lineId: number | null;
  version: number | null;
  correction: boolean;
  pending: "save" | Pick<CountLine, "id" | "version" | "name"> | null;
}

export function requestId(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 15) | 64;
  bytes[8] = (bytes[8]! & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

export function blankDraft(): CountDraft {
  return {
    name: "",
    unit: "шт",
    price: "",
    quantity: "",
    byAmount: false,
    enteredAmount: "",
    lineId: null,
    version: null,
    correction: false,
    pending: null,
    requestId: requestId(),
  };
}

export function hasInput(form: CountDraft): boolean {
  return Boolean(
    form.lineId ||
      form.name ||
      form.price ||
      form.quantity ||
      form.enteredAmount ||
      form.unit !== "шт" ||
      form.pending,
  );
}

export function nameKey(name: string): string {
  return name.trim().replace(/\s+/gu, " ").toLowerCase().replaceAll("ё", "е");
}

export function lineCount(count: number): string {
  return `${count} ${plural(count, "позиция", "позиции", "позиций")}`;
}

type BalanceFields = Pick<CountLine, "price" | "unit" | "quantity" | "amount">;

export function stocktakeQuantity({ price, unit, quantity, amount }: BalanceFields): string | null {
  const value = quantity === null ? formatQuantityFromAmount(amount, price) : formatNumber(quantity);
  return value === null ? null : `${value} ${unit}`;
}

export function stocktakeBalance(line: BalanceFields): string {
  const units = stocktakeQuantity(line);
  const money = line.quantity === null ? `${formatMoney(line.amount)} ₽` : null;
  return [units, money].filter(Boolean).join(" · ");
}

export function stocktakeHint(
  { price, unit }: Pick<CountLine, "price" | "unit">,
  quantity: string | null,
  amount: string | null,
): string {
  const unitPrice = price === null ? "" : `${formatMoney(price)} ₽ / ${unit}`;
  if (amount === null) return unitPrice || `${unit} · Цена не указана`;
  const balance = stocktakeBalance({ price, unit, quantity, amount });
  return [`Уже в переучёте · ${balance}`, unitPrice].filter(Boolean).join(" · ");
}

export function restoreDraft(key: string): CountDraft {
  try {
    const raw = sessionStorage.getItem(key) ?? localStorage.getItem(key);
    if (raw) {
      const form = JSON.parse(raw);
      if (
        typeof form.requestId === "string" &&
        typeof form.name === "string" &&
        typeof form.price === "string" &&
        typeof form.quantity === "string" &&
        ["шт", "кг"].includes(form.unit)
      ) {
        // older drafts kept the pending deletion in the editor fields
        const removal = form.pending === "delete"
          ? { id: form.lineId, version: form.version, name: "" }
          : form.pending;
        const validRemoval = Number.isSafeInteger(removal?.id) && removal.id > 0
          && Number.isSafeInteger(removal.version) && removal.version > 0
          && typeof removal.name === "string";
        return {
          ...form,
          pending: form.pending === "save" || validRemoval ? removal : null,
          byAmount: form.byAmount === true,
          enteredAmount: typeof form.enteredAmount === "string" ? form.enteredAmount : "",
        };
      }
    }
  } catch {
    // storage can be unavailable in private browsing
  }
  return blankDraft();
}

export function persistDraft(key: string, form: CountDraft, previousId: string): boolean {
  try {
    if (hasInput(form)) {
      const json = JSON.stringify(form);
      localStorage.setItem(key, json);
      sessionStorage.setItem(key, json);
    } else {
      sessionStorage.removeItem(key);
      const saved = localStorage.getItem(key);
      if (saved && JSON.parse(saved).requestId === previousId) localStorage.removeItem(key);
    }
    return true;
  } catch {
    return false;
  }
}

export async function changeLine(id: number, form: CountDraft) {
  const removal = form.pending === "save" ? null : form.pending;
  const lineId = removal?.id ?? form.lineId;
  const method = removal ? "DELETE" : lineId ? "PUT" : "POST";
  const suffix = lineId ? `/${lineId}` : "";
  const path = `/stocktakes/${id}/lines${suffix}${form.correction ? "?correction=true" : ""}`;
  const ack = await request<{ document_id: number; line_id: number } | null>(method, path, {
    request_id: form.requestId,
    ...(lineId && { version: removal?.version ?? form.version }),
    ...(!removal && {
      name: form.name,
      price: form.price.trim() || null,
      unit: form.unit,
      ...(form.byAmount
        ? { entered_amount: form.enteredAmount.trim() }
        : { quantity: form.quantity.trim() }),
    }),
  });
  if (
    ack?.document_id !== id || !Number.isSafeInteger(ack.line_id) ||
    (lineId !== null && ack.line_id !== lineId)
  ) {
    throw new Error(removal ? "Сервер не подтвердил удаление позиции" : "Сервер не подтвердил сохранение строки");
  }
  return ack;
}
