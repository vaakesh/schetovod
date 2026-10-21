import { useCallback, useEffect, useState } from "react";

import { getLedger, reverseEntry } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import LedgerEntryDialog from "../components/LedgerEntryDialog";
import LedgerOperation from "../components/LedgerOperation";
import RevaluationDialog from "../components/RevaluationDialog";
import { formatDate, formatMoney, formatSigned } from "../format";
import { KIND_LABELS, touchesCash, touchesStock } from "../ledger";
import { message } from "../message";
import type { Route } from "../router";
import type { LedgerEntry, ManualKind } from "../types";

interface Props {
  go: (route: Route) => void;
  ask: Ask;
}

const PAGE = 50;

const STOCK_ACTIONS: ManualKind[] = ["sale", "write_off", "stocktake"];
const CASH_ACTIONS: ManualKind[] = ["cash_in", "cash_out", "cash_count"];

// an invoice is never reversed, a reversal and a reversed entry are final
function reversible(entry: LedgerEntry): boolean {
  return entry.kind !== "invoice" && entry.reverses_id === null && entry.reversed_by_id === null;
}

export default function LedgerPage({ go, ask }: Props) {
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [balance, setBalance] = useState<string | null>(null);
  const [cashBalance, setCashBalance] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [dialog, setDialog] = useState<ManualKind | "revaluation" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const page = await getLedger(PAGE, 0);
      setEntries(page.entries);
      setBalance(page.balance);
      setCashBalance(page.cash_balance);
      setHasMore(page.has_more);
    } catch (reason) {
      setError(message(reason));
    }
  }, []);

  function action(kind: ManualKind) {
    return (
      <button
        key={kind}
        type="button"
        className="button button-soft"
        onClick={() => {
          setError(null);
          setDialog(kind);
        }}
      >
        {KIND_LABELS[kind]}
      </button>
    );
  }

  useEffect(() => {
    void load();
  }, [load]);

  async function more() {
    if (!entries) {
      return;
    }
    setLoadingMore(true);
    try {
      const page = await getLedger(PAGE, entries.length);
      setEntries([...entries, ...page.entries]);
      setHasMore(page.has_more);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setLoadingMore(false);
    }
  }

  async function reverse(entry: LedgerEntry) {
    const ok = await ask({
      title: `Сторнировать запись №${entry.id}?`,
      text: "Появится обратная запись той же датой, исходная останется в журнале.",
      action: "Сторнировать",
      danger: true,
    });
    if (!ok) {
      return;
    }
    setError(null);
    try {
      await reverseEntry(entry.id);
      await load();
    } catch (reason) {
      setError(message(reason));
    }
  }

  return (
    <main className="page">
      <section className="ledger-head">
        <div className="ledger-balances">
          <div>
            <div className="ledger-label">Товар в рознице</div>
            <div className="ledger-balance">{balance === null ? "—" : `${formatMoney(balance)} ₽`}</div>
          </div>
          <div>
            <div className="ledger-label">В кассе</div>
            <div className="ledger-balance">{cashBalance === null ? "—" : `${formatMoney(cashBalance)} ₽`}</div>
          </div>
        </div>
        <div className="ledger-action-groups">
          <div className="ledger-actions">
            {STOCK_ACTIONS.map(action)}
            <button
              type="button"
              className="button button-soft"
              onClick={() => {
                setError(null);
                setDialog("revaluation");
              }}
            >
              {KIND_LABELS.revaluation}
            </button>
          </div>
          <div className="ledger-actions">{CASH_ACTIONS.map(action)}</div>
        </div>
      </section>

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      <section className="sheet">
        <div className="table-wrap">
          <table className="list ledger">
            <thead>
              <tr>
                <th className="num">№</th>
                <th>Дата</th>
                <th>Операция</th>
                <th>Комментарий</th>
                <th className="num">Товар</th>
                <th className="num">Остаток</th>
                <th className="num">Касса</th>
                <th className="num">В кассе</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {entries?.map((entry) => {
                const cancelled = entry.reverses_id !== null || entry.reversed_by_id !== null;
                return (
                  <tr key={entry.id} className={cancelled ? "list-row cancelled" : "list-row"}>
                    {/* the number a reversal refers to */}
                    <td className="num muted-cell nowrap">{entry.id}</td>
                    <td className="nowrap">{formatDate(entry.occurred_on)}</td>
                    <td className="op">
                      <LedgerOperation entry={entry} go={go} />
                    </td>
                    <td className="ledger-comment">{entry.comment}</td>
                    <td className="num strong nowrap">{touchesStock(entry) && formatSigned(entry.amount)}</td>
                    <td className="num muted-cell nowrap">{formatMoney(entry.balance_after)}</td>
                    <td className="num strong nowrap">{touchesCash(entry) && formatSigned(entry.cash)}</td>
                    <td className="num muted-cell nowrap">{formatMoney(entry.cash_after)}</td>
                    <td className="row-actions">
                      {reversible(entry) && (
                        <button type="button" className="row-action" onClick={() => reverse(entry)}>
                          Сторно
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {entries?.length === 0 && <p className="list-empty">Записей пока нет</p>}
      </section>

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
            void load();
          }}
        />
      )}
      {dialog && dialog !== "revaluation" && (
        <LedgerEntryDialog
          kind={dialog}
          onClose={() => setDialog(null)}
          onPosted={() => {
            setDialog(null);
            void load();
          }}
        />
      )}
    </main>
  );
}
