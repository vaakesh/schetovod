import { formatDate, formatMoney, formatSigned } from "../format";
import { touchesCash, touchesStock } from "../ledger";
import type { Route } from "../router";
import type { LedgerEntry } from "../types";
import LedgerOperation from "./LedgerOperation";

interface Props {
  entries: LedgerEntry[] | null;
  go: (route: Route) => void;
  empty: string;
  // without it the table has no action column
  onReverse?: (entry: LedgerEntry) => void;
  // the rows to highlight, just loaded from the cash register
  imported?: Set<number>;
}

// an invoice is never reversed, a reversal and a reversed entry are final
function reversible(entry: LedgerEntry): boolean {
  return entry.kind !== "invoice" && entry.reverses_id === null && entry.reversed_by_id === null;
}

export default function LedgerTable({ entries, go, empty, onReverse, imported }: Props) {
  return (
    <section className="sheet">
      <div className="table-wrap">
        <table className="list ledger">
          <thead>
            <tr>
              <th className="num">№</th>
              <th>Дата</th>
              <th>Операция</th>
              <th className="ledger-comment">Комментарий</th>
              <th className="num">Товар</th>
              <th className="num ledger-after">Остаток</th>
              <th className="num">Касса</th>
              <th className="num ledger-after">В кассе</th>
              {onReverse && <th />}
            </tr>
          </thead>
          <tbody>
            {entries?.map((entry) => {
              const cancelled = entry.reverses_id !== null || entry.reversed_by_id !== null;
              const rowClass = ["list-row", cancelled && "cancelled", imported?.has(entry.id) && "imported"]
                .filter(Boolean)
                .join(" ");
              return (
                <tr key={entry.id} className={rowClass}>
                  {/* the number a reversal refers to */}
                  <td className="num muted-cell nowrap">{entry.id}</td>
                  <td className="nowrap">{formatDate(entry.occurred_on)}</td>
                  <td className="op">
                    <LedgerOperation entry={entry} go={go} />
                    {/* takes the place of the comment column on a narrow screen */}
                    {entry.comment && <span className="op-comment">{entry.comment}</span>}
                  </td>
                  <td className="ledger-comment">{entry.comment}</td>
                  <td className="num strong nowrap">
                    {touchesStock(entry) && formatSigned(entry.amount)}
                    {/* takes the place of the balance columns on a narrow screen */}
                    <span className="op-after">{formatMoney(entry.balance_after)}</span>
                  </td>
                  <td className="num muted-cell nowrap ledger-after">{formatMoney(entry.balance_after)}</td>
                  <td className="num strong nowrap">
                    {touchesCash(entry) && formatSigned(entry.cash)}
                    <span className="op-after">{formatMoney(entry.cash_after)}</span>
                  </td>
                  <td className="num muted-cell nowrap ledger-after">{formatMoney(entry.cash_after)}</td>
                  {onReverse && (
                    <td className="row-actions">
                      {reversible(entry) && (
                        <button type="button" className="row-action" onClick={() => onReverse(entry)}>
                          Сторно
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {entries?.length === 0 && <p className="list-empty">{empty}</p>}
    </section>
  );
}
