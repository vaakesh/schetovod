import type {
  Catalog,
  ConfirmedInvoice,
  DraftForm,
  InvoiceDraft,
  InvoiceList,
  InvoiceSort,
  InvoiceStatus,
  LedgerBalance,
  LedgerPage,
  LedgerPosted,
  LedgerReport,
  ManualKind,
  PaymentCreate,
  PostedInvoice,
  ProductEdit,
  ProductSummary,
  RevaluationCreate,
  RevaluationLineOut,
  SupplierEdit,
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
  line_no: "Номер позиции",
  name: "Название",
  inn: "ИНН",
  quantity: "Кол-во",
  unit: "Ед.",
  vat_percent: "НДС",
  cost_price_total: "Сумма к оплате",
  retail_price: "Розничная цена",
  revalue_quantity: "Осталось старого товара",
  new_price: "Новая цена",
  product_id: "Товар",
  cost_total: "Итог к оплате",
  base_total: "Итог без НДС",
  items: "Строки",
  totals: "Итоги",
  occurred_on: "Дата",
  paid_on: "Дата оплаты",
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
  // only the confirmed invoices not paid in full
  unpaid: boolean;
  q: string;
  sort: InvoiceSort;
  limit: number;
  offset: number;
}): Promise<InvoiceList> {
  // false is the default, it is left out of the query
  return request("GET", `/invoice${query({ ...params, unpaid: params.unpaid ? "true" : null })}`);
}

export function getPosted(id: number): Promise<PostedInvoice> {
  return request("GET", `/invoice/${id}/confirmed`);
}

export function getLedger(limit: number, offset: number): Promise<LedgerPage> {
  return request("GET", `/ledger${query({ limit, offset })}`);
}

export function getBalance(on: string | null): Promise<LedgerBalance> {
  return request("GET", `/ledger/balance${query({ on })}`);
}

const LEDGER_PATHS: Record<ManualKind, string> = {
  sale: "/ledger/sale",
  write_off: "/ledger/write-off",
  stocktake: "/ledger/stocktake",
  cash_in: "/ledger/cash-in",
  cash_out: "/ledger/cash-out",
  cash_count: "/ledger/cash-count",
};

export function addLedgerEntry(kind: ManualKind, body: unknown): Promise<LedgerPosted> {
  return request("POST", LEDGER_PATHS[kind], body);
}

export function addRevaluation(body: RevaluationCreate): Promise<LedgerPosted> {
  return request("POST", "/ledger/revaluation", body);
}

export function getRevaluationLines(entryId: number): Promise<RevaluationLineOut[]> {
  return request("GET", `/ledger/${entryId}/revaluation`);
}

export function getReport(dateFrom: string, dateTo: string): Promise<LedgerReport> {
  return request("GET", `/ledger/report${query({ date_from: dateFrom, date_to: dateTo })}`);
}

// a plain link downloads the file, the browser takes the name from the response
export function reportXlsxUrl(dateFrom: string, dateTo: string): string {
  return `/api/ledger/report.xlsx${query({ date_from: dateFrom, date_to: dateTo })}`;
}

export function reportPdfUrl(dateFrom: string, dateTo: string): string {
  return `/api/ledger/report.pdf${query({ date_from: dateFrom, date_to: dateTo })}`;
}

export function addPayment(invoiceId: number, body: PaymentCreate): Promise<PostedInvoice> {
  return request("POST", `/invoice/${invoiceId}/payments`, body);
}

export function deletePayment(invoiceId: number, paymentId: number): Promise<PostedInvoice> {
  return request("DELETE", `/invoice/${invoiceId}/payments/${paymentId}`);
}

export function reverseEntry(id: number): Promise<LedgerPosted> {
  return request("POST", `/ledger/${id}/reverse`);
}

export function searchSuppliers(q: string, limit?: number): Promise<SupplierSummary[]> {
  return request("GET", `/supplier${query({ q: q.trim(), limit })}`);
}

export function searchProducts(supplierId: number, q: string): Promise<ProductSummary[]> {
  return request("GET", `/supplier/${supplierId}/products${query({ q: q.trim() })}`);
}

// every supplier with every product, without paging
export function getCatalog(): Promise<Catalog> {
  return request("GET", "/catalog");
}

// the price the user saw goes along, a tag for an older price is rejected
export async function markPriceTag(
  id: number,
  hasPriceTag: boolean,
  retailPrice: number,
): Promise<void> {
  await request("PUT", `/product/${id}/price-tag`, {
    has_price_tag: hasPriceTag,
    retail_price: retailPrice,
  });
}

// null when the price changed without a revaluation
export function editProduct(id: number, body: ProductEdit): Promise<LedgerPosted | null> {
  return request("PUT", `/product/${id}`, body);
}

export function editSupplier(id: number, body: SupplierEdit): Promise<SupplierSummary> {
  return request("PUT", `/supplier/${id}`, body);
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

export function confirmInvoice(id: number, occurredOn: string): Promise<ConfirmedInvoice> {
  return request("POST", `/invoice/${id}/confirm`, { occurred_on: occurredOn });
}

export function declineInvoice(id: number): Promise<null> {
  return request("POST", `/invoice/${id}/decline`);
}
