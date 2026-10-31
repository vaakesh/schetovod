import { useEffect, useState, type MouseEvent } from "react";

import { ensureSession, getReport, reportPdfUrl, reportXlsxUrl } from "../api";
import LedgerTable from "../components/LedgerTable";
import PageHead from "../components/PageHead";
import PeriodFields from "../components/PeriodFields";
import { formatDate, formatMoney, formatSigned } from "../format";
import { fromInputDate, todayInput } from "../form";
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

  // the token may have expired, a bare link would then save the error instead of the file
  function download(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    const url = event.currentTarget.href;
    ensureSession()
      .then(() => window.location.assign(url))
      .catch((reason) => setError(message(reason)));
  }

  return (
    <main className="page">
      <PageHead title="Отчёт">
        <PeriodFields start={start} end={end} onStart={setStart} onEnd={setEnd} />
        {dateFrom !== null && dateTo !== null && report && (
          <>
            <a
              className="button button-soft"
              href={reportPdfUrl(dateFrom, dateTo)}
              download
              onClick={download}
            >
              Скачать pdf
            </a>
            <a
              className="button button-soft"
              href={reportXlsxUrl(dateFrom, dateTo)}
              download
              onClick={download}
            >
              Скачать xlsx
            </a>
          </>
        )}
      </PageHead>

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

          <LedgerTable entries={report.entries} go={go} empty="За период записей нет" />
        </>
      )}
    </main>
  );
}
