import type {
  AddedProducts,
  Catalog,
  ConfirmedInvoice,
  DraftForm,
  ExpenseForm,
  InvoiceDraft,
  InvoiceList,
  InvoiceSort,
  InvoiceStatus,
  BatchKind,
  LedgerBalance,
  LedgerBatchLine,
  LedgerPage,
  LedgerPosted,
  SingleKind,
  LedgerReport,
  Order,
  OrderList,
  PaymentCreate,
  PostedInvoice,
  ProductEdit,
  ProductSummary,
  ProfitReport,
  RevaluationCreate,
  RevaluationLineOut,
  ShiftImportResult,
  SupplierEdit,
  SupplierSummary,
  TrafficForecast,
  TrafficReport,
  UserSummary,
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
  // the limit of nginx answers without a json body
  if (status === 429) {
    return "Слишком много попыток входа, подождите минуту";
  }
  return `Сервер ответил ошибкой ${status}`;
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  // the browser sets the multipart content type with its boundary itself
  const form = body instanceof FormData;
  try {
    return await fetch(`/api${path}`, {
      method,
      headers: body === undefined || form ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    });
  } catch {
    throw new Error("Сервер недоступен");
  }
}

// a 401 here is an answer about the credentials, not about the session
const NO_REFRESH = ["/auth/login", "/auth/refresh"];

let refreshing: Promise<boolean> | null = null;

// the requests of a page fail together, they share one exchange of the token
function refreshSession(): Promise<boolean> {
  refreshing ??= send("POST", "/auth/refresh")
    .then(async (response) => {
      if (response.ok || response.status === 401) {
        return response.ok;
      }
      // the server is down, the session may be alive
      throw new Error(errorText(response.status, await response.json().catch(() => null)));
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

const sessionLost = new Set<() => void>();

export function onSessionLost(listener: () => void): () => void {
  sessionLost.add(listener);
  return () => sessionLost.delete(listener);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response = await send(method, path, body);
  if (response.status === 401 && !NO_REFRESH.includes(path)) {
    if (await refreshSession()) {
      response = await send(method, path, body);
    }
    if (response.status === 401) {
      sessionLost.forEach((listener) => listener());
    }
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorText(response.status, data));
  }
  return data as T;
}

export function login(body: { login: string; password: string }): Promise<UserSummary> {
  return request("POST", "/auth/login", body);
}

export function logout(): Promise<void> {
  return request("POST", "/auth/logout");
}

export function getMe(): Promise<UserSummary> {
  return request("GET", "/auth/me");
}

// a plain link can not refresh the token, the request before it does
export async function ensureSession(): Promise<void> {
  await getMe();
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

const LEDGER_PATHS: Record<SingleKind, string> = {
  sale: "/ledger/sale",
  stocktake: "/ledger/stocktake",
  cash_count: "/ledger/cash-count",
};

export function addLedgerBatch(kind: BatchKind, entries: LedgerBatchLine[]): Promise<unknown> {
  return request("POST", "/ledger/batch", { kind, entries });
}

export function getLedgerComments(kind: BatchKind): Promise<string[]> {
  return request("GET", `/ledger/comments${query({ kind })}`);
}

export function addLedgerEntry(kind: SingleKind, body: unknown): Promise<LedgerPosted> {
  return request("POST", LEDGER_PATHS[kind], body);
}

export function importShifts(dateFrom: string, dateTo: string): Promise<ShiftImportResult> {
  return request("POST", "/ledger/import-shifts", { date_from: dateFrom, date_to: dateTo });
}

export function getTrafficReport(dateFrom: string, dateTo: string): Promise<TrafficReport> {
  return request("GET", `/traffic/report${query({ date_from: dateFrom, date_to: dateTo })}`);
}

export function getTrafficForecast(dateFrom: string, dateTo: string): Promise<TrafficForecast> {
  return request("GET", `/traffic/forecast${query({ date_from: dateFrom, date_to: dateTo })}`);
}

export function getProfitReport(): Promise<ProfitReport> {
  return request("GET", "/profit");
}

export function addExpense(body: ExpenseForm): Promise<ProfitReport> {
  return request("POST", "/profit/expenses", body);
}

export function editExpense(id: number, body: ExpenseForm): Promise<ProfitReport> {
  return request("PUT", `/profit/expenses/${id}`, body);
}

export function stopExpense(id: number): Promise<ProfitReport> {
  return request("DELETE", `/profit/expenses/${id}`);
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

// the browser downloads the file by the url and takes the name from the response
export function reportXlsxUrl(dateFrom: string, dateTo: string): string {
  return `/api/ledger/report.xlsx${query({ date_from: dateFrom, date_to: dateTo })}`;
}

export function reportPdfUrl(dateFrom: string, dateTo: string): string {
  return `/api/ledger/report.pdf${query({ date_from: dateFrom, date_to: dateTo })}`;
}

// the confirmed invoices without the retail prices, the browser opens the file to print
export function invoicesPrintUrl(ids: number[]): string {
  const search = new URLSearchParams();
  for (const id of ids) {
    search.append("ids", String(id));
  }
  return `/api/invoices/print.pdf?${search.toString()}`;
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

// the cart, null while nothing is in it
export function getDraftOrder(): Promise<Order | null> {
  return request("GET", "/order/draft");
}

// the whole quantity, the first product starts the cart
export function setOrderItem(productId: number, quantity: string): Promise<Order> {
  return request("PUT", `/order/draft/items/${productId}`, { quantity });
}

// null when the last line is gone, the cart is deleted with it
export function removeOrderItem(productId: number): Promise<Order | null> {
  return request("DELETE", `/order/draft/items/${productId}`);
}

export async function clearDraftOrder(): Promise<void> {
  await request("DELETE", "/order/draft");
}

export function confirmOrder(): Promise<Order> {
  return request("POST", "/order/draft/confirm");
}

// the confirmed orders, the newest first
export function listOrders(limit: number, offset: number): Promise<OrderList> {
  return request("GET", `/orders${query({ limit, offset })}`);
}

export function getOrder(id: number): Promise<Order> {
  return request("GET", `/order/${id}`);
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

export function addInvoiceProducts(id: number): Promise<AddedProducts> {
  return request("POST", `/invoice/${id}/products`);
}

export function declineInvoice(id: number): Promise<null> {
  return request("POST", `/invoice/${id}/decline`);
}
