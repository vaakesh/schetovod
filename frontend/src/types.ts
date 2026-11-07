// mirrors backend domain schemas, decimals come as strings

export type PriceTagUnit = "piece" | "weight";
export type PriceTagOrigin = "maker" | "country";

// everything printed on a shelf tag
export interface PriceTagFields {
  width_mm: number;
  height_mm: number;
  unit: PriceTagUnit;
  // the weight or volume in the header, null shows only the unit
  pack: string | null;
  name: string;
  subtitle: string | null;
  // null leaves the price blank for a price written by hand
  price: string | null;
  origin: PriceTagOrigin;
  origin_name: string;
}

export interface PriceTag extends PriceTagFields {
  id: number;
}

export interface PriceTagPrintRow extends PriceTagFields {
  // copies of the same tag
  quantity: number;
}

export interface SupplierExtraction {
  name: string | null;
  inn: string | null;
}

export interface InvoiceItemExtraction {
  line_no: string | null;
  name: string | null;
  quantity: string | null;
  unit: string | null;
  base_price: string | null;
  base_price_total: string | null;
  cost_price: string | null;
  cost_price_total: string | null;
  vat_percent: string | null;
}

export interface TotalsExtraction {
  base_total: string | null;
  cost_total: string | null;
}

export interface InvoiceExtraction {
  supplier: SupplierExtraction;
  invoice_number: string | null;
  invoice_date: string | null;
  items: InvoiceItemExtraction[];
  totals: TotalsExtraction;
}

export interface SupplierRef {
  id: number;
}

export interface NewSupplier {
  name: string;
  inn: string | null;
}

export interface FormLine {
  line_no: number;
  name: string | null;
  quantity: string | null;
  unit: string | null;
  vat_percent: string | null;
  cost_price_total: string | null;
  product_id: number | null;
  retail_price: number | null;
  // the old stock on the shelf that takes the new price
  revalue_quantity: string | null;
}

export interface FormTotals {
  cost_total: string | null;
  base_total: string | null;
}

export interface DraftForm {
  invoice_number: string | null;
  invoice_date: string | null;
  supplier: SupplierRef | NewSupplier | null;
  totals: FormTotals;
  lines: FormLine[];
}

export interface Issue {
  line: number | null;
  message: string;
  blocking: boolean;
  // set for the issues shown their own way, e.g. similar_product
  code: string | null;
}

export interface SimilarProduct {
  id: number;
  name: string;
  // percent of matching characters
  similarity: number;
}

export interface DraftLine {
  line: number;
  cost_price: string | null;
  base_price: string | null;
  base_price_total: string | null;
  product_id: number | null;
  product_name: string | null;
  new_product: boolean;
  markup_pct: string | null;
  retail_price: string | null;
  retail_price_total: string | null;
  // the cost with VAT of the last delivery of the product, null when it is the same or unknown
  previous_cost_price: string | null;
  // the shelf price of the product when the line changes it
  previous_retail_price: string | null;
  // catalog products with a close name while the line has none, most similar first
  similar: SimilarProduct[];
}

export interface DraftTotals {
  base_total: string | null;
  cost_total: string | null;
  retail_total: string | null;
}

export interface UserSummary {
  id: number;
  login: string;
}

export interface SupplierSummary {
  id: number;
  name: string;
  // printed in the reports instead of the full name
  short_name: string | null;
  inn: string | null;
}

export interface SupplierEdit {
  name: string;
  short_name: string | null;
  inn: string | null;
}

export interface ProductSummary {
  id: number;
  name: string;
  markup_pct: string;
  // from the last posted line, null while the product was never posted
  unit: string | null;
  vat_percent: string | null;
  cost_price: string | null;
  // the shelf price
  retail_price: string | null;
}

export interface CatalogProduct extends ProductSummary {
  supplier_id: number;
  // other names the product was printed with, the name itself is not repeated
  spellings: string[];
  // a shelf tag with the current retail price is hanging
  has_price_tag: boolean;
}

export interface Catalog {
  // every supplier, including the ones without products yet
  suppliers: SupplierSummary[];
  products: CatalogProduct[];
}

export type OrderStatus = "draft" | "confirmed";

export interface OrderLine {
  product_id: number;
  name: string;
  supplier_id: number;
  supplier_name: string;
  quantity: string;
  // a draft shows the last posted line, a confirmed order the one it was confirmed with,
  // null while the product was never posted
  unit: string | null;
  cost_price: string | null;
  cost_total: string | null;
}

export interface Order {
  id: number;
  status: OrderStatus;
  // null while the order is a draft
  confirmed_at: string | null;
  // by supplier, then by name
  lines: OrderLine[];
  // the lines with a cost price only
  total: string;
  // some lines have no cost price, the total is short of them
  has_unpriced: boolean;
}

export interface OrderListItem {
  id: number;
  confirmed_at: string;
  lines: number;
  supplier_names: string[];
  total: string;
}

export interface OrderList {
  items: OrderListItem[];
  has_more: boolean;
}

export interface SupplierCandidate extends SupplierSummary {
  matched_lines: number;
}

export interface AddedProducts {
  created: number;
  // known products of the draft, left as they are
  skipped: number;
}

export interface ConfirmedInvoice {
  id: number;
  ledger_entry_id: number;
  retail_total: string;
  // null when nothing was revalued
  revaluation: string | null;
  balance: string;
}

export type InvoiceStatus = "draft" | "confirmed" | "declined" | "reversed";

export interface ReversedInvoice {
  id: number;
  reversal_entry_id: number;
  // the copy to fix, null when no copy was asked for
  draft_id: number | null;
  balance: string;
}

// the newest uploads first, or the biggest debt first
export type InvoiceSort = "newest" | "debt";

export interface InvoiceListItem {
  id: number;
  status: InvoiceStatus;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  retail_total: string | null;
  // owed to the supplier and not paid yet, null until the invoice is confirmed
  debt: string | null;
  lines: number;
  created_at: string;
}

export interface InvoiceList {
  items: InvoiceListItem[];
  has_more: boolean;
}

export interface PostedLine {
  line_no: number;
  name: string;
  product_name: string;
  quantity: string;
  unit: string | null;
  vat_percent: string | null;
  base_price: string | null;
  cost_price: string;
  cost_price_total: string;
  markup_pct: string;
  retail_price: string;
  retail_price_total: string;
}

export interface PostedInvoice {
  id: number;
  // confirmed, or reversed once its posting was cancelled
  status: InvoiceStatus;
  // why the invoice can not be reversed now, null when it can
  reverse_block: string | null;
  invoice_number: string;
  invoice_date: string;
  supplier: SupplierSummary;
  lines: PostedLine[];
  // owed to the supplier
  cost_total: string;
  retail_total: string;
  ledger_entry_id: number;
  paid: string;
  debt: string;
  payments: Payment[];
}

export interface Payment {
  id: number;
  paid_on: string;
  amount: string;
  comment: string | null;
}

export interface PaymentCreate {
  paid_on: string | null;
  amount: string;
  comment: string | null;
}

export type LedgerKind =
  | "invoice"
  | "sale"
  | "write_off"
  | "stock_in"
  | "stocktake"
  | "revaluation"
  | "cash_in"
  | "cash_out"
  | "cash_count";

// the kinds entered by hand in the entry dialog, a revaluation has its own form
export type ManualKind = Exclude<LedgerKind, "invoice" | "revaluation">;

// the kinds with a sum and a comment, one window takes several of them
export type BatchKind = "write_off" | "stock_in" | "cash_in" | "cash_out";

export type SingleKind = Exclude<ManualKind, BatchKind>;

export interface LedgerBatchLine {
  occurred_on: string | null;
  amount: string | null;
  comment: string | null;
}

export interface LedgerEntry {
  id: number;
  occurred_on: string;
  kind: LedgerKind;
  // signed, positive brings stock in
  amount: string;
  // signed, positive brings cash into the till
  cash: string;
  balance_after: string;
  cash_after: string;
  comment: string | null;
  reverses_id: number | null;
  reversed_by_id: number | null;
  invoice_id: number | null;
  invoice_number: string | null;
  supplier_name: string | null;
}

export interface LedgerPage {
  balance: string;
  cash_balance: string;
  entries: LedgerEntry[];
  has_more: boolean;
}

export interface LedgerBalance {
  balance: string;
  cash_balance: string;
  // the latest stocktake, no stock entry may be dated before it
  closed_on: string | null;
  // the latest cash count, no cash entry may be dated before it
  cash_closed_on: string | null;
}

export interface LedgerPosted {
  id: number;
  amount: string;
  cash: string;
  balance: string;
  cash_balance: string;
}

export interface ImportedShift {
  entry_id: number;
  shift_number: number;
  occurred_on: string;
  cash: string;
  card: string;
}

export interface SkippedShift {
  shift_number: number;
  occurred_on: string | null;
  reason: string;
}

export interface ShiftImportResult {
  imported: ImportedShift[];
  skipped: SkippedShift[];
}

export type ExpenseBasis = "month" | "year" | "work_day" | "revenue_percent" | "card_percent";

export interface ExpenseForm {
  name: string;
  basis: ExpenseBasis;
  amount: string;
  // the first day of the month
  starts_on: string;
}

export interface ExpenseOut extends ExpenseForm {
  id: number;
}

export interface ExpenseCharge {
  name: string;
  total: string;
}

export interface ProfitMonth {
  month: string;
  in_progress: boolean;
  work_days: number;
  revenue: string;
  card: string;
  margin: string | null;
  margin_estimated: boolean;
  gross: string | null;
  stock_difference: string | null;
  write_offs: string | null;
  charges: ExpenseCharge[];
  expenses: string;
  profit: string | null;
}

export interface ProfitMargin {
  percent: string;
  cost: string;
  retail: string;
  date_from: string;
  date_to: string;
}

export interface ProfitReport {
  last_receipt_at: string | null;
  // newest first
  months: ProfitMonth[];
  average_profit: string | null;
  break_even_day: string | null;
  margin: ProfitMargin | null;
  expenses: ExpenseOut[];
}

export interface TrafficSummary {
  receipts: number;
  days: number;
  per_day: number | null;
  revenue: string;
  average_check: string | null;
  peak_hour: number | null;
  peak_weekday: number | null;
}

export interface HourLoad {
  hour: number;
  receipts: number;
  average_check: string | null;
}

export interface WeekdayLoad {
  // monday is 0
  weekday: number;
  days: number;
  receipts: number;
  average_check: string | null;
}

export interface HeatCell {
  weekday: number;
  hour: number;
  receipts: number;
}

export interface DayLoad {
  day: string;
  receipts: number;
  revenue: string;
  trend: number | null;
}

export interface ForecastValue {
  expected: number;
  low: number;
  high: number;
}

export interface HourForecast {
  hour: number;
  receipts: ForecastValue;
  revenue: ForecastValue;
  fact_receipts: number | null;
  fact_revenue: string | null;
}

export interface DayFact {
  until_hour: number | null;
  receipts: number;
  revenue: string;
  plan_receipts: ForecastValue;
  plan_revenue: ForecastValue;
}

export interface DayForecast {
  day: string;
  weekday: number;
  based_on: number;
  receipts: ForecastValue | null;
  revenue: ForecastValue | null;
  hours: HourForecast[];
  fact: DayFact | null;
}

export interface ForecastScore {
  accuracy: number;
  bias: number;
}

export interface ForecastAccuracy {
  days: number;
  receipts: ForecastScore | null;
  revenue: ForecastScore | null;
}

export interface TrafficForecast {
  date_from: string;
  date_to: string;
  days: DayForecast[];
  accuracy: ForecastAccuracy | null;
}

export interface TrafficReport {
  date_from: string;
  date_to: string;
  last_receipt_at: string | null;
  summary: TrafficSummary;
  by_hour: HourLoad[];
  by_weekday: WeekdayLoad[];
  heatmap: HeatCell[];
  daily: DayLoad[];
}

export interface RevaluationLine {
  product_id: number;
  quantity: string;
  // whole rubles
  new_price: number;
}

export interface RevaluationCreate {
  occurred_on: string;
  comment: string | null;
  lines: RevaluationLine[];
}

export interface ProductRevaluation {
  occurred_on: string;
  // the old stock counted on the shelf
  quantity: string;
  comment: string | null;
}

export interface ProductEdit {
  // the old name stays as another spelling of the product
  name: string;
  retail_price: number;
  // null when there is no old stock, the price then changes without a ledger entry
  revaluation: ProductRevaluation | null;
}

export interface RevaluationLineOut {
  product_id: number;
  product_name: string;
  quantity: string;
  old_price: string;
  new_price: string;
  // signed, what the line adds to the stock
  amount: string;
}

export interface LedgerReport {
  date_from: string;
  date_to: string;
  opening: string;
  // signed sums of the period, a reversal counts with the kind it cancels
  invoices: string;
  sales: string;
  write_offs: string;
  stock_ins: string;
  stocktakes: string;
  revaluations: string;
  closing: string;
  cash_opening: string;
  // the sales split into the till and the bank account
  sales_cash: string;
  sales_card: string;
  cash_ins: string;
  cash_outs: string;
  cash_counts: string;
  cash_closing: string;
  // in the ledger order
  entries: LedgerEntry[];
}

export interface InvoiceDraft {
  id: number;
  ready: boolean;
  products_ready: boolean;
  issues: Issue[];
  form: DraftForm;
  lines: DraftLine[];
  totals: DraftTotals;
  supplier: SupplierSummary | null;
  supplier_candidates: SupplierCandidate[];
  extraction: InvoiceExtraction;
}
