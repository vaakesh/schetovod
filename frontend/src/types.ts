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

export interface SupplierCandidate extends SupplierSummary {
  matched_lines: number;
}

export interface ConfirmedInvoice {
  id: number;
  ledger_entry_id: number;
  retail_total: string;
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
