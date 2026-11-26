import { useEffect, useRef, useState } from "react";

import { getLedger, reverseEntry, reverseInvoice } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import LedgerBatchDialog from "../components/LedgerBatchDialog";
import LedgerEntryDialog from "../components/LedgerEntryDialog";
import LedgerSortField from "../components/LedgerSortField";
import LedgerTable from "../components/LedgerTable";
import PageHead from "../components/PageHead";
import RevaluationDialog from "../components/RevaluationDialog";
import ShiftImportDialog from "../components/ShiftImportDialog";
import { formatMoney } from "../format";
import { KIND_LABELS } from "../ledger";
import { message } from "../message";
import type { Route } from "../router";
import type { BatchKind, LedgerEntry, LedgerSort, ManualKind } from "../types";

interface Props {
  go: (route: Route) => void;
  ask: Ask;
  shiftImportEnabled: boolean;
  sort: LedgerSort;
  onSort: (sort: LedgerSort) => void;
}

const PAGE = 50;

const STOCK_ACTIONS: ManualKind[] = ["sale", "write_off", "stock_in", "stocktake"];
const CASH_ACTIONS: ManualKind[] = ["cash_in", "cash_out", "cash_count"];
const BATCH_KINDS: string[] = ["write_off", "stock_in", "cash_in", "cash_out"] satisfies BatchKind[];

function isBatch(kind: string): kind is BatchKind {
  return BATCH_KINDS.includes(kind);
}

export default function LedgerPage({ go, ask, shiftImportEnabled, sort, onSort }: Props) {
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [balance, setBalance] = useState<string | null>(null);
  const [cashBalance, setCashBalance] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [dialog, setDialog] = useState<ManualKind | "revaluation" | "shifts" | null>(null);
  // the rows loaded from the cash register, the page forgets them when it is left
  const [imported, setImported] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const requestId = useRef(0);

  function reload() {
    setRevision((current) => current + 1);
  }

  function open(next: ManualKind | "revaluation" | "shifts") {
    setError(null);
    setDialog(next);
  }

  function action(kind: ManualKind | "revaluation") {
    return (
      <button key={kind} type="button" className="button button-soft" onClick={() => open(kind)}>
        {KIND_LABELS[kind]}
      </button>
    );
  }

  useEffect(() => {
    const id = ++requestId.current;
    setEntries(null);
    setHasMore(false);
    setLoadingMore(false);
    setError(null);
    getLedger(PAGE, 0, sort)
      .then((page) => {
        if (id !== requestId.current) return;
        setEntries(page.entries);
        setBalance(page.balance);
        setCashBalance(page.cash_balance);
        setHasMore(page.has_more);
      })
      .catch((reason) => {
        if (id === requestId.current) setError(message(reason));
      });
    return () => {
      requestId.current++;
    };
  }, [sort, revision]);

  async function more() {
    if (!entries || loadingMore) {
      return;
    }
    setLoadingMore(true);
    const id = ++requestId.current;
    try {
      const page = await getLedger(PAGE, entries.length, sort);
      if (id !== requestId.current) return;
      setEntries([...entries, ...page.entries]);
      setHasMore(page.has_more);
    } catch (reason) {
      if (id === requestId.current) setError(message(reason));
    } finally {
      if (id === requestId.current) setLoadingMore(false);
    }
  }

  async function reverse(entry: LedgerEntry) {
    // an invoice is reversed with its revaluation, the invoice turns into a reversed one
    const invoiceId = entry.kind === "invoice" ? entry.invoice_id : null;
    const ok = await ask({
      title:
        invoiceId !== null
          ? `Сторнировать накладную ${entry.invoice_number ?? `№${invoiceId}`}?`
          : `Сторнировать запись №${entry.id}?`,
      text:
        invoiceId !== null
          ? "Приход отменится встречной записью той же датой, переоценка по накладной тоже. Цены товаров в каталоге не изменятся."
          : "Появится обратная запись той же датой, исходная останется в журнале.",
      action: "Сторнировать",
      danger: true,
    });
    if (!ok) {
      return;
    }
    setError(null);
    try {
      if (invoiceId !== null) {
        await reverseInvoice(invoiceId, false);
      } else {
        await reverseEntry(entry.id);
      }
      reload();
    } catch (reason) {
      setError(message(reason));
    }
  }

  return (
    <main className="page">
      <PageHead title="Журнал">
        <LedgerSortField sort={sort} onSort={onSort} />
        {shiftImportEnabled && (
          <button type="button" className="button button-soft" onClick={() => open("shifts")}>
            Загрузить из кассы
          </button>
        )}
      </PageHead>

      {/* each balance with the operations that change it */}
      <div className="ledger-books">
        <section className="sheet ledger-book">
          <div>
            <div className="ledger-label">Товар в рознице</div>
            <div className="ledger-balance">{balance === null ? "—" : `${formatMoney(balance)} ₽`}</div>
          </div>
          <div className="ledger-actions">
            {STOCK_ACTIONS.map(action)}
            {action("revaluation")}
          </div>
        </section>
        <section className="sheet ledger-book">
          <div>
            <div className="ledger-label">В кассе</div>
            <div className="ledger-balance">{cashBalance === null ? "—" : `${formatMoney(cashBalance)} ₽`}</div>
          </div>
          <div className="ledger-actions">{CASH_ACTIONS.map(action)}</div>
        </section>
      </div>

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      <LedgerTable
        entries={entries}
        go={go}
        empty="Записей пока нет"
        onReverse={(entry) => void reverse(entry)}
        imported={imported}
      />

      {hasMore && (
        <div className="more">
          <button type="button" className="button button-ghost" disabled={loadingMore} onClick={more}>
            Показать ещё
          </button>
        </div>
      )}

      {dialog === "revaluation" && (
        <RevaluationDialog
          onClose={() => setDialog(null)}
          onPosted={() => {
            setDialog(null);
            reload();
          }}
        />
      )}
      {shiftImportEnabled && dialog === "shifts" && (
        <ShiftImportDialog
          onClose={() => setDialog(null)}
          onImported={(entryIds) => {
            setImported((rows) => new Set([...rows, ...entryIds]));
            reload();
          }}
        />
      )}
      {dialog && isBatch(dialog) && (
        <LedgerBatchDialog
          kind={dialog}
          onClose={() => setDialog(null)}
          onPosted={() => {
            setDialog(null);
            reload();
          }}
        />
      )}
      {dialog && dialog !== "revaluation" && dialog !== "shifts" && !isBatch(dialog) && (
        <LedgerEntryDialog
          kind={dialog}
          onClose={() => setDialog(null)}
          onPosted={() => {
            setDialog(null);
            reload();
          }}
        />
      )}
    </main>
  );
}
