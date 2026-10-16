// mirrors app/schemas.py, decimals come as strings

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

export interface SupplierSummary {
  id: number;
  name: string;
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
}

export interface Catalog {
  // every supplier, including the ones without products yet
  suppliers: SupplierSummary[];
  products: CatalogProduct[];
}

export interface SupplierCandidate extends SupplierSummary {
  matched_lines: number;
}

export interface ConfirmedInvoice {
  id: number;
  ledger_entry_id: number;
  retail_total: string;
  // null when nothing was revalued
  revaluation: string | null;
  balance: string;
}

export type InvoiceStatus = "draft" | "confirmed" | "declined";

export interface InvoiceListItem {
  id: number;
  status: InvoiceStatus;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  retail_total: string | null;
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
  invoice_number: string;
  invoice_date: string;
  supplier: SupplierSummary;
  lines: PostedLine[];
  cost_total: string;
  retail_total: string;
  ledger_entry_id: number;
}

export type LedgerKind = "invoice" | "sale" | "write_off" | "stocktake" | "revaluation";

// the kinds entered by hand as one amount, a revaluation has its own form
export type ManualKind = Exclude<LedgerKind, "invoice" | "revaluation">;

export interface LedgerEntry {
  id: number;
  occurred_on: string;
  kind: LedgerKind;
  // signed, positive brings stock in
  amount: string;
  balance_after: string;
  comment: string | null;
  reverses_id: number | null;
  reversed_by_id: number | null;
  invoice_id: number | null;
  invoice_number: string | null;
  supplier_name: string | null;
}

export interface LedgerPage {
  balance: string;
  entries: LedgerEntry[];
  has_more: boolean;
}

export interface LedgerBalance {
  balance: string;
  closed_on: string | null;
}

export interface LedgerPosted {
  id: number;
  amount: string;
  balance: string;
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
  stocktakes: string;
  revaluations: string;
  closing: string;
  // in the ledger order
  entries: LedgerEntry[];
}

export interface InvoiceDraft {
  id: number;
  ready: boolean;
  issues: Issue[];
  form: DraftForm;
  lines: DraftLine[];
  totals: DraftTotals;
  supplier: SupplierSummary | null;
  supplier_candidates: SupplierCandidate[];
  extraction: InvoiceExtraction;
}
