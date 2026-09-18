import { formatMoney } from "../format";
import { KIND_LABELS } from "../ledger";
import type { Route } from "../router";
import type { LedgerEntry } from "../types";

interface Props {
  entry: LedgerEntry;
  go: (route: Route) => void;
}

// what the entry is, an invoice links to the posted invoice
export default function LedgerOperation({ entry, go }: Props) {
  if (entry.kind === "invoice" && entry.invoice_id !== null) {
    const invoiceId = entry.invoice_id;
    return (
      <>
        <a
          className="op-link"
          href={`#/posted/${invoiceId}`}
          onClick={(event) => {
            event.preventDefault();
            go({ page: "posted", id: invoiceId });
          }}
        >
          Накладная №{entry.invoice_number}
        </a>
        <span className="op-meta">{entry.supplier_name}</span>
      </>
    );
  }
  return (
    <>
      <span className="op-title">
        {KIND_LABELS[entry.kind]}
        {entry.reverses_id !== null && <span className="tag-soft">сторно №{entry.reverses_id}</span>}
        {entry.reversed_by_id !== null && <span className="tag-soft">сторнирована</span>}
      </span>
      {/* what was counted and what the books said, the entry is the difference */}
      {entry.kind === "stocktake" && entry.reverses_id === null && (
        <span className="op-meta">
          насчитали {formatMoney(entry.balance_after)} · по учёту{" "}
          {formatMoney(Number(entry.balance_after) - Number(entry.amount))}
        </span>
      )}
    </>
  );
}
