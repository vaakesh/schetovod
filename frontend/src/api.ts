import type {
  ConfirmedInvoice,
  DraftForm,
  InvoiceDraft,
  InvoiceList,
  InvoiceStatus,
  PostedInvoice,
  ProductSummary,
  SupplierSummary,
} from "./types";

interface ValidationError {
  loc: (string | number)[];
  type: string;
}

const FIELD_LABELS: Record<string, string> = {
  invoice_number: "Номер накладной",
  invoice_date: "Дата накладной",
  supplier: "Продавец",
  name: "Название",
  inn: "ИНН",
  quantity: "Кол-во",
  unit: "Ед.",
  vat_percent: "НДС",
  cost_price_total: "Сумма к оплате",
  retail_price: "Розничная цена",
  new_price: "Новая цена",
  product_id: "Товар",
  cost_total: "Итог к оплате",
  base_total: "Итог без НДС",
  items: "Строки",
  totals: "Итоги",
  occurred_on: "Дата",
  amount: "Сумма",
  counted: "Насчитали",
  comment: "Комментарий",
};

function problem(type: string): string {
  if (type === "missing" || type === "string_too_short") {
    return "не заполнено";
  }
  if (type === "string_pattern_mismatch") {
    return "неверный формат";
  }
  return "неверное значение";
}

function where(loc: (string | number)[]): string {
  const parts: string[] = [];
  for (let index = 0; index < loc.length; index++) {
    const part = loc[index]!;
    if (part === "body" || part === "totals" || /^[A-Z]/.test(String(part))) {
      continue;
    }
    if ((part === "lines" || part === "items") && typeof loc[index + 1] === "number") {
      parts.push(`Строка ${(loc[index + 1] as number) + 1}`);
      index++;
      continue;
    }
    if (part === "supplier" && loc.length > index + 1) {
      parts.push("Продавец");
      continue;
    }
    parts.push(FIELD_LABELS[String(part)] ?? String(part));
  }
  return parts.join(" · ");
}

function errorText(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  // a 422 from FastAPI lists every field that did not pass
  if (Array.isArray(detail)) {
    const lines = (detail as ValidationError[])
      // a union reports a miss for each variant, the reference by id is not what the form sends
      .filter((error) => !error.loc.includes("SupplierRef"))
      .map((error) => `${where(error.loc)}: ${problem(error.type)}`);
    return [...new Set(lines)].join("\n");
  }
  return `Сервер ответил ошибкой ${status}`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  // the browser sets the multipart content type with its boundary itself
  const form = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined || form ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    });
  } catch {
    throw new Error("Сервер недоступен");
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorText(response.status, data));
  }
  return data as T;
}

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function listInvoices(params: {
  status: InvoiceStatus | null;
  q: string;
  limit: number;
  offset: number;
}): Promise<InvoiceList> {
  return request("GET", `/invoice${query(params)}`);
}

export function getPosted(id: number): Promise<PostedInvoice> {
  return request("GET", `/invoice/${id}/confirmed`);
}

export function searchSuppliers(q: string, limit?: number): Promise<SupplierSummary[]> {
  return request("GET", `/supplier${query({ q: q.trim(), limit })}`);
}

export function searchProducts(supplierId: number, q: string): Promise<ProductSummary[]> {
  return request("GET", `/supplier/${supplierId}/products${query({ q: q.trim() })}`);
}

export function receiveInvoice(body: unknown): Promise<InvoiceDraft> {
  return request("POST", "/invoice", body);
}

// the photos are pages of one invoice, the backend recognizes them in one request
export function recognizeInvoice(files: File[]): Promise<InvoiceDraft> {
  const body = new FormData();
  for (const file of files) {
    body.append("files", file);
  }
  return request("POST", "/invoice/image", body);
}

export function getDraft(id: number): Promise<InvoiceDraft> {
  return request("GET", `/invoice/${id}`);
}

export function saveForm(id: number, form: DraftForm): Promise<InvoiceDraft> {
  return request("PUT", `/invoice/${id}`, form);
}

export function confirmInvoice(id: number): Promise<ConfirmedInvoice> {
  return request("POST", `/invoice/${id}/confirm`);
}

export function declineInvoice(id: number): Promise<null> {
  return request("POST", `/invoice/${id}/decline`);
}
