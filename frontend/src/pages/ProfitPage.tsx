import { useEffect, useState } from "react";

import { getProfitReport, stopExpense } from "../api";
import type { Ask } from "../components/ConfirmDialog";
import ExpenseDialog from "../components/ExpenseDialog";
import Icon from "../components/icons";
import PageHead from "../components/PageHead";
import { formatDate, formatDateTime } from "../format";
import { message } from "../message";
import { expenseRate, monthLabel } from "../profit";
import { formatRubles } from "../traffic";
import type { ExpenseOut, ProfitMonth, ProfitReport } from "../types";

function formatPercent(value: string | null): string {
  return value === null ? "—" : `${value.replace(".", ",")}%`;
}

function profitClass(value: string | null): string {
  return value !== null && Number(value) < 0 ? "profit-loss" : "";
}

function MonthDetails({ month }: { month: ProfitMonth }) {
  const stock = month.stock_difference !== null && Number(month.stock_difference) !== 0;
  return (
    <section className="sheet traffic-card">
      <h2 className="traffic-title">Как посчитан {monthLabel(month.month)}</h2>
      <p className="traffic-note">
        {month.in_progress
          ? "Месяц идёт, аренда, свет и другие постоянные расходы взяты за прошедшие дни"
          : `Рабочих дней: ${month.work_days}`}
      </p>
      <dl className="profit-lines">
        <div>
          <dt>Выручка</dt>
          <dd>{formatRubles(month.revenue)}</dd>
        </div>
        <div>
          <dt>Валовая прибыль, маржа {formatPercent(month.margin)}</dt>
          <dd>{formatRubles(month.gross)}</dd>
        </div>
        {stock && (
          <div>
            <dt>Недостача или излишек на переучёте</dt>
            <dd>{formatRubles(month.stock_difference)}</dd>
          </div>
        )}
        {month.charges.map((charge) => (
          <div key={charge.name}>
            <dt>{charge.name}</dt>
            <dd>−{formatRubles(charge.total)}</dd>
          </div>
        ))}
        <div className="profit-total">
          <dt>Прибыль</dt>
          <dd className={profitClass(month.profit)}>{formatRubles(month.profit)}</dd>
        </div>
      </dl>
      {month.write_offs !== null && Number(month.write_offs) !== 0 && (
        <p className="traffic-note profit-aside">
          Для сведения: списания на {formatRubles(month.write_offs)} по себестоимости, в прибыль не
          входят
        </p>
      )}
    </section>
  );
}

interface Props {
  ask: Ask;
}

export default function ProfitPage({ ask }: Props) {
  const [report, setReport] = useState<ProfitReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // undefined while the dialog is closed, null adds a new expense
  const [editing, setEditing] = useState<ExpenseOut | null | undefined>(undefined);

  useEffect(() => {
    let current = true;
    getProfitReport()
      .then((next) => current && setReport(next))
      .catch((reason) => current && setError(message(reason)));
    return () => {
      current = false;
    };
  }, []);

  async function stop(expense: ExpenseOut) {
    const confirmed = await ask({
      title: `Убрать расход «${expense.name}»?`,
      text: "С этого месяца он перестанет считаться, прошлые месяцы останутся как есть.",
      action: "Убрать",
      danger: true,
    });
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      setReport(await stopExpense(expense.id));
    } catch (reason) {
      setError(message(reason));
    }
  }

  const months = report?.months ?? [];
  const latest = months[0];
  const lastFinished = months.find((month) => !month.in_progress) ?? latest;
  const shown = months.find((month) => month.month === selected) ?? lastFinished;
  const lastReceipt = report?.last_receipt_at ?? null;

  return (
    <main className="page">
      <PageHead
        title="Прибыль"
        meta={
          report &&
          (lastReceipt ? `Чеки загружены по ${formatDateTime(lastReceipt)}` : "Чеки ещё не загружены")
        }
      />

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      {report && (
        <>
          {latest ? (
            <>
              <dl className="traffic-tiles">
                <div className="sheet traffic-tile">
                  <dt className="profit-month-tile">
                    {monthLabel(latest.month)}
                    {latest.in_progress ? ", пока" : ""}
                  </dt>
                  <dd className={profitClass(latest.profit)}>{formatRubles(latest.profit)}</dd>
                </div>
                <div className="sheet traffic-tile">
                  <dt>В среднем за месяц</dt>
                  <dd className={profitClass(report.average_profit)}>
                    {formatRubles(report.average_profit)}
                  </dd>
                </div>
                <div className="sheet traffic-tile">
                  <dt>Маржа</dt>
                  <dd>{report.margin ? formatPercent(report.margin.percent) : "—"}</dd>
                </div>
                <div className="sheet traffic-tile">
                  <dt>Нужно в рабочий день</dt>
                  <dd>{formatRubles(report.break_even_day)}</dd>
                </div>
              </dl>

              <section className="sheet traffic-card">
                <h2 className="traffic-title">По месяцам</h2>
                <p className="traffic-note">Нажмите на месяц, чтобы увидеть расчёт</p>
                <div className="table-wrap">
                  <table className="list profit-table">
                    <thead>
                      <tr>
                        <th>Месяц</th>
                        <th className="num">Дней</th>
                        <th className="num">Выручка</th>
                        <th className="num">Маржа</th>
                        <th className="num">Валовая прибыль</th>
                        <th className="num">Расходы</th>
                        <th className="num">Прибыль</th>
                      </tr>
                    </thead>
                    <tbody>
                      {months.map((month) => (
                        <tr
                          key={month.month}
                          className={month.month === shown?.month ? "active" : undefined}
                        >
                          <td>
                            <button
                              type="button"
                              className="profit-month"
                              aria-pressed={month.month === shown?.month}
                              onClick={() => setSelected(month.month)}
                            >
                              {monthLabel(month.month)}
                              {month.in_progress ? ", идёт" : ""}
                            </button>
                          </td>
                          <td className="num">{month.work_days}</td>
                          <td className="num">{formatRubles(month.revenue)}</td>
                          <td className="num">
                            {formatPercent(month.margin)}
                            {month.margin_estimated ? "*" : ""}
                          </td>
                          <td className="num">{formatRubles(month.gross)}</td>
                          <td className="num">{formatRubles(month.expenses)}</td>
                          <td className={`num profit-value ${profitClass(month.profit)}`}>
                            {formatRubles(month.profit)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {shown && <MonthDetails month={shown} />}
            </>
          ) : (
            <section className="sheet traffic-card">
              <p className="list-empty">
                Прибыль появится после загрузки чеков из кассы, она идёт автоматически
              </p>
            </section>
          )}

          <section className="sheet traffic-card">
            <div className="traffic-head">
              <div>
                <h2 className="traffic-title">Операционные расходы</h2>
                <p className="traffic-note">
                  Новая сумма действует с выбранного месяца, прошлые месяцы не меняются
                </p>
              </div>
              <button
                type="button"
                className="button button-soft"
                onClick={() => setEditing(null)}
              >
                <Icon name="plus" size={18} />
                Добавить
              </button>
            </div>
            {report.expenses.length === 0 ? (
              <p className="list-empty">Расходов пока нет</p>
            ) : (
              <ul className="profit-expenses">
                {report.expenses.map((expense) => (
                  <li key={expense.id}>
                    <span className="profit-expense-name">{expense.name}</span>
                    <span className="profit-expense-rate">{expenseRate(expense)}</span>
                    <span className="profit-expense-actions">
                      <button
                        type="button"
                        className="button button-ghost"
                        onClick={() => setEditing(expense)}
                      >
                        Изменить
                      </button>
                      <button
                        type="button"
                        className="button button-ghost"
                        aria-label={`Убрать расход ${expense.name}`}
                        title="Убрать"
                        onClick={() => void stop(expense)}
                      >
                        <Icon name="close" size={18} />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <p className="traffic-note traffic-foot">
            Прибыль считается приблизительно: продаж по товарам нет, поэтому маржа взята по
            накладным, ходовые товары весят больше.
            {report.margin &&
              ` Сейчас это накладные с ${formatDate(report.margin.date_from)} по ${formatDate(report.margin.date_to)}.`}{" "}
            Накладные, деньги из кассы и списания расходом не считаются.
            {months.some((month) => month.margin_estimated) &&
              " * За этот месяц накладных нет, взята ближайшая известная маржа."}
          </p>
        </>
      )}

      {editing !== undefined && (
        <ExpenseDialog
          expense={editing}
          onClose={() => setEditing(undefined)}
          onSaved={(next) => {
            setReport(next);
            setEditing(undefined);
          }}
        />
      )}
    </main>
  );
}
