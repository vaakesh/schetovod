import { useState } from "react";

import { getRevaluationLines } from "../api";
import { formatMoney, formatNumber, formatSigned } from "../format";
import { KIND_LABELS } from "../ledger";
import { message } from "../message";
import type { Route } from "../router";
import type { LedgerEntry, RevaluationLineOut } from "../types";

interface Props {
  entry: LedgerEntry;
  go: (route: Route) => void;
}

// the products of a revaluation, loaded when opened
function RevaluationLines({ entryId }: { entryId: number }) {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<RevaluationLineOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setOpen(!open);
    if (open || lines !== null) {
      return;
    }
    try {
      setLines(await getRevaluationLines(entryId));
    } catch (reason) {
      setError(message(reason));
    }
  }

  return (
    <>
      <button type="button" className="op-toggle" aria-expanded={open} onClick={() => void toggle()}>
        {open ? "скрыть товары" : "что переоценили"}
      </button>
      {open && (
        <span className="op-lines">
          {error && <span className="op-error">{error}</span>}
          {lines === null && !error && <span className="op-meta">загрузка…</span>}
          {lines?.map((line) => (
            <span key={line.product_id} className="op-line">
              <span className="op-line-name">{line.product_name}</span>
              <span className="op-line-figures">
                {formatNumber(line.quantity)} × {formatNumber(line.old_price)} →{" "}
                {formatNumber(line.new_price)} ₽ = {formatSigned(line.amount)}
              </span>
            </span>
          ))}
        </span>
      )}
    </>
  );
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
        {entry.reversed_by_id !== null && (
          <span className="tag-soft">сторнирована записью №{entry.reversed_by_id}</span>
        )}
      </span>
      {/* what was counted and what the books said, the entry is the difference */}
      {entry.kind === "stocktake" && entry.reverses_id === null && (
        <span className="op-meta">
          насчитали {formatMoney(entry.balance_after)} · по учёту{" "}
          {formatMoney(Number(entry.balance_after) - Number(entry.amount))}
        </span>
      )}
      {entry.kind === "cash_count" && entry.reverses_id === null && (
        <span className="op-meta">
          в кассе {formatMoney(entry.cash_after)} · по учёту{" "}
          {formatMoney(Number(entry.cash_after) - Number(entry.cash))}
        </span>
      )}
      {/* the sale takes the whole amount from the stock, the till gets the cash part */}
      {entry.kind === "sale" && entry.reverses_id === null && (
        <span className="op-meta">
          наличные {formatMoney(entry.cash)} · безнал{" "}
          {formatMoney(-Number(entry.amount) - Number(entry.cash))}
        </span>
      )}
      {entry.kind === "revaluation" && <RevaluationLines entryId={entry.id} />}
    </>
  );
}
