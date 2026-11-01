import { useEffect, useState } from "react";

import { getTrafficForecast } from "../api";
import { formatDate, plural } from "../format";
import { fromInputDate, shiftInput, todayInput } from "../form";
import { message } from "../message";
import {
  WEEKDAYS,
  WEEKDAYS_SHORT,
  formatPeople,
  formatRubles,
  formatThousands,
} from "../traffic";
import type { TrafficForecast } from "../types";
import ForecastChart from "./ForecastChart";
import PeriodFields from "./PeriodFields";

const DEFAULT_PERIOD_DAYS = 56;
// below it a median is a guess
const RELIABLE_DAYS = 3;
const NEAR_DAYS = ["Сегодня", "Завтра"];

export default function ForecastCard() {
  const [start, setStart] = useState(() => shiftInput(todayInput(), -DEFAULT_PERIOD_DAYS));
  const [end, setEnd] = useState(() => shiftInput(todayInput(), -1));
  const [forecast, setForecast] = useState<TrafficForecast | null>(null);
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
    getTrafficForecast(dateFrom, dateTo)
      .then((next) => current && setForecast(next))
      .catch((reason) => {
        if (current) {
          setForecast(null);
          setError(message(reason));
        }
      });
    return () => {
      current = false;
    };
  }, [dateFrom, dateTo]);

  const day = forecast?.days[selected];
  const hasForecast = forecast?.days.some((next) => next.based_on > 0) ?? false;

  return (
    <section className="sheet traffic-card">
      <div className="traffic-head">
        <div>
          <h2 className="traffic-title">Прогноз покупателей и кассы</h2>
          <p className="traffic-note">По таким же дням недели за выбранный период</p>
        </div>
        <PeriodFields
          start={start}
          end={end}
          max={shiftInput(todayInput(), -1)}
          onStart={setStart}
          onEnd={setEnd}
        />
      </div>

      {error && (
        <div className="alert">
          <pre>{error}</pre>
        </div>
      )}

      {forecast && !hasForecast && <p className="list-empty">За этот период чеков нет</p>}

      {forecast && hasForecast && day && (
        <>
          <div className="traffic-days">
            {forecast.days.map((next, index) => (
              <button
                key={next.day}
                type="button"
                className={index === selected ? "traffic-day active" : "traffic-day"}
                aria-pressed={index === selected}
                onClick={() => setSelected(index)}
              >
                <span className="traffic-day-name">
                  {NEAR_DAYS[index] ?? WEEKDAYS_SHORT[next.weekday]}
                </span>
                <span className="traffic-day-date">{formatDate(next.day).slice(0, 5)}</span>
                <strong>{formatPeople(next.receipts?.expected ?? null)}</strong>
                <span className="traffic-day-money">
                  {formatRubles(next.revenue?.expected ?? null)}
                </span>
              </button>
            ))}
          </div>
          {day.receipts === null || day.revenue === null ? (
            <p className="list-empty">По этому дню недели за выбранный период данных нет</p>
          ) : (
            <>
              <p className="traffic-note">
                {WEEKDAYS[day.weekday]}, {formatDate(day.day)}: обычно{" "}
                {formatPeople(day.receipts.low)}–{formatPeople(day.receipts.high)} покупателей и{" "}
                {formatRubles(day.revenue.low)}–{formatRubles(day.revenue.high)} выручки. По{" "}
                {day.based_on}{" "}
                {plural(day.based_on, "прошлому дню", "прошлым дням", "прошлым дням")} с{" "}
                {formatDate(forecast.date_from)} по {formatDate(forecast.date_to)}.
                {day.based_on < RELIABLE_DAYS && " Мало данных, прогноз примерный."} Прогноз не
                учитывает праздники.
              </p>
              <div className="traffic-pair">
                <div>
                  <h3 className="traffic-subtitle">Покупатели по часам</h3>
                  <ForecastChart
                    key={day.day}
                    hours={day.hours.map(({ hour, receipts }) => ({ hour, value: receipts }))}
                    label={`Прогноз покупателей по часам на ${formatDate(day.day)}`}
                    legend="Ожидается покупателей"
                    format={formatPeople}
                  />
                </div>
                <div>
                  <h3 className="traffic-subtitle">Выручка по часам</h3>
                  <ForecastChart
                    key={day.day}
                    hours={day.hours.map(({ hour, revenue }) => ({ hour, value: revenue }))}
                    label={`Прогноз выручки по часам на ${formatDate(day.day)}`}
                    legend="Ожидается выручки"
                    format={formatRubles}
                    formatTick={formatThousands}
                  />
                </div>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
