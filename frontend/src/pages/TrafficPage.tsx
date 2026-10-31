import { useEffect, useState } from "react";

import { getTrafficReport } from "../api";
import BarsChart from "../components/BarsChart";
import ForecastChart from "../components/ForecastChart";
import LoadHeatmap from "../components/LoadHeatmap";
import PageHead from "../components/PageHead";
import PeriodFields from "../components/PeriodFields";
import TrendChart from "../components/TrendChart";
import { formatDate, formatDateTime, plural } from "../format";
import { fromInputDate, shiftInput, todayInput } from "../form";
import { message } from "../message";
import {
  WEEKDAYS,
  WEEKDAYS_SHORT,
  formatCount,
  formatPeople,
  formatRubles,
  hourRange,
} from "../traffic";
import type { TrafficReport } from "../types";

const DEFAULT_PERIOD_DAYS = 56;
// below it a median is a guess
const RELIABLE_DAYS = 3;

export default function TrafficPage() {
  const [start, setStart] = useState(() => shiftInput(todayInput(), -DEFAULT_PERIOD_DAYS));
  const [end, setEnd] = useState(() => shiftInput(todayInput(), -1));
  const [report, setReport] = useState<TrafficReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);

  const dateFrom = fromInputDate(start);
  const dateTo = fromInputDate(end);

  useEffect(() => {
    if (dateFrom === null || dateTo === null) {
      return;
    }
    let current = true;
    setError(null);
    getTrafficReport(dateFrom, dateTo)
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

  const lastReceipt = report?.last_receipt_at ?? null;
  const summary = report?.summary;
  const forecastDay = report?.forecast[selected];
  const hasForecast = report?.forecast.some((day) => day.based_on > 0) ?? false;

  return (
    <main className="page">
      <PageHead
        title="Покупатели"
        meta={
          report &&
          (lastReceipt ? `Чеки загружены по ${formatDateTime(lastReceipt)}` : "Чеки ещё не загружены")
        }
      >
        <PeriodFields start={start} end={end} onStart={setStart} onEnd={setEnd} />
      </PageHead>

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      {report && summary && (
        <>
          {hasForecast && forecastDay && (
            <section className="sheet traffic-card">
              <h2 className="traffic-title">Прогноз покупателей</h2>
              <div className="traffic-days">
                {report.forecast.map((day, index) => (
                  <button
                    key={day.day}
                    type="button"
                    className={index === selected ? "traffic-day active" : "traffic-day"}
                    aria-pressed={index === selected}
                    onClick={() => setSelected(index)}
                  >
                    <span className="traffic-day-name">
                      {index === 0 ? "Завтра" : WEEKDAYS_SHORT[day.weekday]}
                    </span>
                    <span className="traffic-day-date">{formatDate(day.day).slice(0, 5)}</span>
                    <strong>{formatPeople(day.receipts)}</strong>
                  </button>
                ))}
              </div>
              {forecastDay.based_on === 0 ? (
                <p className="list-empty">По этому дню недели данных нет</p>
              ) : (
                <>
                  <p className="traffic-note">
                    {WEEKDAYS[forecastDay.weekday]}, {formatDate(forecastDay.day)}: обычно{" "}
                    {formatPeople(forecastDay.low)}–{formatPeople(forecastDay.high)} покупателей.
                    {" "}По {forecastDay.based_on}{" "}
                    {plural(forecastDay.based_on, "прошлому дню", "прошлым дням", "прошлым дням")}.
                    {forecastDay.based_on < RELIABLE_DAYS && " Мало данных, прогноз примерный."}
                  </p>
                  <ForecastChart
                    key={forecastDay.day}
                    hours={forecastDay.hours}
                    label={`Прогноз покупателей по часам на ${formatDate(forecastDay.day)}`}
                  />
                </>
              )}
            </section>
          )}

          {summary.days === 0 ? (
            <section className="sheet traffic-card">
              <p className="list-empty">
                {lastReceipt
                  ? "За этот период чеков нет"
                  : "Графики появятся после загрузки чеков из кассы, она идёт автоматически"}
              </p>
            </section>
          ) : (
            <>
              <dl className="traffic-tiles">
                <div className="sheet traffic-tile">
                  <dt>Покупателей в день</dt>
                  <dd>{formatCount(summary.per_day)}</dd>
                </div>
                <div className="sheet traffic-tile">
                  <dt>Средний чек</dt>
                  <dd>{formatRubles(summary.average_check)}</dd>
                </div>
                <div className="sheet traffic-tile">
                  <dt>Пиковый час</dt>
                  <dd>{summary.peak_hour === null ? "—" : hourRange(summary.peak_hour)}</dd>
                </div>
                <div className="sheet traffic-tile">
                  <dt>Самый загруженный день</dt>
                  <dd>{summary.peak_weekday === null ? "—" : WEEKDAYS[summary.peak_weekday]}</dd>
                </div>
              </dl>

              <section className="sheet traffic-card">
                <h2 className="traffic-title">Загрузка по дням недели и часам</h2>
                <p className="traffic-note">Среднее число покупателей в час, чем насыщеннее цвет, тем больше</p>
                <LoadHeatmap cells={report.heatmap} />
              </section>

              <div className="traffic-pair">
                <section className="sheet traffic-card">
                  <h2 className="traffic-title">Средняя загрузка по часам</h2>
                  <p className="traffic-note">Покупателей за час</p>
                  <BarsChart
                    label="Средняя загрузка по часам"
                    bars={report.by_hour.map((load) => ({
                      key: load.hour,
                      axis: `${load.hour}:00`,
                      title: hourRange(load.hour),
                      value: load.receipts,
                      shown: formatCount(load.receipts),
                    }))}
                  />
                </section>
                <section className="sheet traffic-card">
                  <h2 className="traffic-title">Средняя загрузка по дням недели</h2>
                  <p className="traffic-note">Покупателей за день</p>
                  <BarsChart
                    label="Средняя загрузка по дням недели"
                    bars={report.by_weekday.map((load) => ({
                      key: load.weekday,
                      axis: WEEKDAYS_SHORT[load.weekday] ?? "",
                      title: WEEKDAYS[load.weekday] ?? "",
                      value: load.days > 0 ? load.receipts : null,
                      shown: load.days > 0 ? formatCount(load.receipts) : "нет данных",
                      detail: load.average_check === null ? undefined : `средний чек ${formatRubles(load.average_check)}`,
                    }))}
                  />
                </section>
              </div>

              <section className="sheet traffic-card">
                <h2 className="traffic-title">Средний чек по часам</h2>
                <p className="traffic-note">Рублей</p>
                <BarsChart
                  label="Средний чек по часам"
                  bars={report.by_hour.map((load) => ({
                    key: load.hour,
                    axis: `${load.hour}:00`,
                    title: hourRange(load.hour),
                    value: load.average_check === null ? null : Number(load.average_check),
                    shown: formatRubles(load.average_check),
                  }))}
                />
              </section>

              <section className="sheet traffic-card">
                <h2 className="traffic-title">Динамика покупателей</h2>
                <TrendChart days={report.daily} />
              </section>

              <p className="traffic-note traffic-foot">
                Один чек считается одним покупателем. Средние считаются по дням с продажами с{" "}
                {formatDate(report.date_from)} по {formatDate(report.date_to)}, сегодняшний день в них
                не входит. Прогноз не учитывает праздники.
              </p>
            </>
          )}
        </>
      )}
    </main>
  );
}
