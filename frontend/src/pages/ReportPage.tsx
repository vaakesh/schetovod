import { useEffect, useState } from "react";

import { getReport, reportPdfUrl, reportXlsxUrl } from "../api";
import LedgerOperation from "../components/LedgerOperation";
import { formatDate, formatMoney, formatSigned } from "../format";
import { fromInputDate, todayInput } from "../form";
import { touchesCash, touchesStock } from "../ledger";
import { message } from "../message";
import type { Route } from "../router";
import type { LedgerReport } from "../types";

interface Props {
  go: (route: Route) => void;
}

// the signed sums between the opening and the closing balance, in the order of the report
type Flow = "invoices" | "sales" | "write_offs" | "stocktakes" | "revaluations";

const FLOWS: { key: Flow; label: string }[] = [
  { key: "invoices", label: "Приход по накладным" },
  { key: "sales", label: "Продажи" },
  { key: "write_offs", label: "Списания" },
  { key: "stocktakes", label: "Переучёты" },
  { key: "revaluations", label: "Переоценка" },
];

type CashFlow = "sales_cash" | "cash_ins" | "cash_outs" | "cash_counts";

const CASH_FLOWS: { key: CashFlow; label: string }[] = [
  { key: "sales_cash", label: "Продажи наличными" },
  { key: "cash_ins", label: "Внесения" },
  { key: "cash_outs", label: "Выдачи" },
  { key: "cash_counts", label: "Сверки кассы" },
];

// the report opens on the current month up to today
function monthStart(): string {
  return `${todayInput().slice(0, 8)}01`;
}

export default function ReportPage({ go }: Props) {
  const [start, setStart] = useState(monthStart);
  const [end, setEnd] = useState(todayInput);
  const [report, setReport] = useState<LedgerReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dateFrom = fromInputDate(start);
  const dateTo = fromInputDate(end);

  useEffect(() => {
    if (dateFrom === null || dateTo === null) {
      return;
    }
    let current = true;
    setError(null);
    getReport(dateFrom, dateTo)
      .then((next) => current && setReport(next))
      .catch((reason) => {
        if (current) {
          setReport(null);
          setError(message(reason));
        }
      });
    return () => {
      current = false;
    };
  }, [dateFrom, dateTo]);

  return (
    <main className="page">
      <section className="ledger-head report-head">
        <div className="report-period">
          <label className="field">
            <span className="field-label">С</span>
            <input
              className="input"
              type="date"
              value={start}
              max={end}
              onChange={(event) => setStart(event.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">По</span>
            <input
              className="input"
              type="date"
              value={end}
              min={start}
              onChange={(event) => setEnd(event.target.value)}
            />
          </label>
        </div>
        {dateFrom !== null && dateTo !== null && report && (
          <>
            <a className="button button-soft" href={reportPdfUrl(dateFrom, dateTo)} download>
              Скачать pdf
            </a>
            <a className="button button-soft" href={reportXlsxUrl(dateFrom, dateTo)} download>
              Скачать xlsx
            </a>
          </>
        )}
      </section>

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      {report && (
        <>
          <div className="report-books">
            <section className="sheet report-totals">
              <dl>
                <div className="report-edge">
                  <dt>Товар на {formatDate(report.date_from)}, начало дня</dt>
                  <dd>{formatMoney(report.opening)} ₽</dd>
                </div>
                {FLOWS.map(({ key, label }) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{formatSigned(report[key])} ₽</dd>
                  </div>
                ))}
                <div className="report-edge">
                  <dt>Товар на {formatDate(report.date_to)}, конец дня</dt>
                  <dd>{formatMoney(report.closing)} ₽</dd>
                </div>
              </dl>
            </section>
            <section className="sheet report-totals">
              <dl>
                <div className="report-edge">
                  <dt>Касса на {formatDate(report.date_from)}, начало дня</dt>
                  <dd>{formatMoney(report.cash_opening)} ₽</dd>
                </div>
                {CASH_FLOWS.map(({ key, label }) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{formatSigned(report[key])} ₽</dd>
                  </div>
                ))}
                <div className="report-edge">
                  <dt>Касса на {formatDate(report.date_to)}, конец дня</dt>
                  <dd>{formatMoney(report.cash_closing)} ₽</dd>
                </div>
                {/* gone to the bank account, not part of the till */}
                <div className="report-aside">
                  <dt>Продажи безналом, на счёт</dt>
                  <dd>{formatMoney(report.sales_card)} ₽</dd>
                </div>
              </dl>
            </section>
          </div>

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
                  </tr>
                </thead>
                <tbody>
                  {report.entries.map((entry) => {
                    const cancelled = entry.reverses_id !== null || entry.reversed_by_id !== null;
                    return (
                      <tr key={entry.id} className={cancelled ? "list-row cancelled" : "list-row"}>
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
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {report.entries.length === 0 && <p className="list-empty">За период записей нет</p>}
          </section>
        </>
      )}
    </main>
  );
}
