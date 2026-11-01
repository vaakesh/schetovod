import { useEffect, useState } from "react";

import { getTrafficForecast } from "../api";
import { formatDate, plural } from "../format";
import { fromInputDate, shiftInput, todayInput } from "../form";
import { message } from "../message";
import {
  WEEKDAYS,
  WEEKDAYS_SHORT,
  dayNumber,
  deviation,
  formatDayNumber,
  formatDeviation,
  formatPeople,
  formatRubles,
  formatThousands,
} from "../traffic";
import type { DayForecast, ForecastScore, ForecastValue, TrafficForecast } from "../types";
import ForecastChart from "./ForecastChart";
import Icon from "./icons";
import PeriodFields from "./PeriodFields";

const DEFAULT_PERIOD_DAYS = 56;
// four weeks of base and a week to forecast, as the api demands
const MIN_PERIOD_DAYS = 35;
// below it a median is a guess
const RELIABLE_DAYS = 3;

function deviationClass(value: number | null): string {
  if (value === null || value === 0) {
    return "traffic-deviation";
  }
  return value > 0 ? "traffic-deviation up" : "traffic-deviation down";
}

function rangeNote(fact: number, plan: ForecastValue): string {
  if (fact < plan.low) {
    return "ниже обычного";
  }
  return fact > plan.high ? "выше обычного" : "в обычных пределах";
}

function biasNote(score: ForecastScore): string {
  const bias = Math.round(Math.abs(score.bias));
  if (bias === 0) {
    return "без перекоса";
  }
  return `факт в среднем на ${bias}% ${score.bias > 0 ? "выше" : "ниже"} прогноза`;
}

interface ResultProps {
  title: string;
  fact: number;
  plan: ForecastValue;
  format: (value: number) => string;
}

function DayResult({ title, fact, plan, format }: ResultProps) {
  const percent = deviation(fact, plan.expected);
  return (
    <div className="traffic-result">
      <dt>{title}</dt>
      <dd>
        {format(fact)} <span className={deviationClass(percent)}>{formatDeviation(percent)}</span>
      </dd>
      <dd className="traffic-result-note">
        при плане {format(plan.expected)}, {rangeNote(fact, plan)}
      </dd>
    </div>
  );
}

interface TileProps {
  day: DayForecast;
  name: string;
  past: boolean;
  active: boolean;
  onSelect: () => void;
}

function DayTile({ day, name, past, active, onSelect }: TileProps) {
  const fact = day.fact;
  const percent = fact && deviation(Number(fact.revenue), fact.plan_revenue.expected);
  return (
    <button
      type="button"
      className={active ? "traffic-day active" : "traffic-day"}
      aria-pressed={active}
      onClick={onSelect}
    >
      <span className="traffic-day-name">{name}</span>
      <span className="traffic-day-date">{formatDate(day.day).slice(0, 5)}</span>
      <strong>{formatPeople(day.receipts?.expected ?? null)}</strong>
      <span className="traffic-day-money">{formatRubles(day.revenue?.expected ?? null)}</span>
      {fact ? (
        <span className="traffic-day-fact">
          <span className="traffic-day-fact-label">факт</span>
          <strong>{formatPeople(fact.receipts)}</strong>
          <span className="traffic-day-money">{formatRubles(fact.revenue)}</span>
          <span className={deviationClass(percent ?? null)}>{formatDeviation(percent ?? null)}</span>
          {fact.until_hour !== null && (
            <span className="traffic-day-money">к {fact.until_hour}:00</span>
          )}
        </span>
      ) : (
        past &&
        day.based_on > 0 && (
          <span className="traffic-day-fact">
            <span className="traffic-day-fact-label">нет продаж</span>
          </span>
        )
      )}
    </button>
  );
}

interface Week {
  monday: number;
  // monday first, a day outside the forecast stays an empty slot
  days: (DayForecast | undefined)[];
}

function weekOf(day: DayForecast): number {
  return dayNumber(day.day) - day.weekday;
}

function calendarWeeks(days: DayForecast[]): Week[] {
  const weeks: Week[] = [];
  for (const day of days) {
    let week = weeks[weeks.length - 1];
    if (week?.monday !== weekOf(day)) {
      week = { monday: weekOf(day), days: Array.from({ length: 7 }) };
      weeks.push(week);
    }
    week.days[day.weekday] = day;
  }
  return weeks;
}

interface WeekRevenue {
  expected: number;
  fact: number | null;
  // the plan of the same days and hours as the fact, a week in progress is not behind the whole week
  plan: number;
}

function weekRevenue(week: Week): WeekRevenue {
  const totals: WeekRevenue = { expected: 0, fact: null, plan: 0 };
  for (const day of week.days) {
    totals.expected += day?.revenue?.expected ?? 0;
    if (day?.fact) {
      totals.fact = (totals.fact ?? 0) + Number(day.fact.revenue);
      totals.plan += day.fact.plan_revenue.expected;
    }
  }
  return totals;
}

export default function ForecastCard() {
  const [start, setStart] = useState(() => shiftInput(todayInput(), -DEFAULT_PERIOD_DAYS));
  const [end, setEnd] = useState(todayInput);
  const [forecast, setForecast] = useState<TrafficForecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const dateFrom = fromInputDate(start);
  const dateTo = fromInputDate(end);
  const tooShort =
    dateFrom !== null &&
    dateTo !== null &&
    dayNumber(dateTo) - dayNumber(dateFrom) + 1 < MIN_PERIOD_DAYS;

  useEffect(() => {
    if (dateFrom === null || dateTo === null || tooShort) {
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
  }, [dateFrom, dateTo, tooShort]);

  const today = fromInputDate(todayInput());
  const tomorrow = fromInputDate(shiftInput(todayInput(), 1));
  const days = forecast?.days ?? [];
  const day =
    days.find((next) => next.day === selected) ??
    days.find((next) => next.day === today) ??
    days[days.length - 1];
  const hasForecast = days.some((next) => next.based_on > 0);
  const accuracy = forecast?.accuracy;
  const fact = day?.fact;
  const untilHour = fact?.until_hour ?? null;
  const measured = untilHour === null ? "за день" : `к ${untilHour}:00`;

  const weeks = calendarWeeks(days);
  const weekIndex = day ? weeks.findIndex((week) => week.monday === weekOf(day)) : -1;
  const week = weeks[weekIndex];
  const revenue = week && weekRevenue(week);
  const weekDeviation =
    revenue && revenue.fact !== null ? deviation(revenue.fact, revenue.plan) : null;

  // the same weekday of the next page, so the charts below always match the week shown
  function turnWeek(step: number) {
    const target = weeks[weekIndex + step];
    const next = target?.days[day?.weekday ?? 0] ?? target?.days.find(Boolean);
    if (next) {
      setSelected(next.day);
    }
  }

  function dayName(next: DayForecast): string {
    if (next.day === today) {
      return "Сегодня";
    }
    return next.day === tomorrow ? "Завтра" : (WEEKDAYS_SHORT[next.weekday] ?? "");
  }

  return (
    <section className="sheet traffic-card">
      <div className="traffic-head">
        <div>
          <h2 className="traffic-title">Прогноз покупателей и кассы</h2>
          <p className="traffic-note">
            Первые четыре недели периода только база, дальше каждый день считается по таким же дням
            недели до него
          </p>
        </div>
        <PeriodFields
          start={start}
          end={end}
          max={todayInput()}
          onStart={setStart}
          onEnd={setEnd}
        />
      </div>

      {error && (
        <div className="alert">
          <pre>{error}</pre>
        </div>
      )}

      {tooShort && (
        <p className="list-empty">
          Нужен период от пяти недель: четыре уходят на базу, с пятой начинается прогноз
        </p>
      )}

      {!tooShort && forecast && !hasForecast && <p className="list-empty">За этот период чеков нет</p>}

      {!tooShort && forecast && hasForecast && day && (
        <>
          {accuracy && (
            <p className="traffic-note">
              Точность за {accuracy.days} {plural(accuracy.days, "день", "дня", "дней")}:
              {accuracy.receipts &&
                ` покупатели ${Math.round(accuracy.receipts.accuracy)}%, ${biasNote(accuracy.receipts)}`}
              {accuracy.receipts && accuracy.revenue && ";"}
              {accuracy.revenue &&
                ` выручка ${Math.round(accuracy.revenue.accuracy)}%, ${biasNote(accuracy.revenue)}`}
              .
            </p>
          )}
          <div className="traffic-week">
            <div className="traffic-week-total">
              <span>Ожидаемая выручка</span>
              <strong>{formatRubles(revenue?.expected ?? null)}</strong>
            </div>
            <div className="traffic-week-turns">
              <button
                type="button"
                className="button button-soft traffic-week-turn"
                aria-label="Предыдущая неделя"
                disabled={weekIndex <= 0}
                onClick={() => turnWeek(-1)}
              >
                <Icon name="chevronLeft" />
              </button>
              {week && (
                <span className="traffic-week-name">
                  {formatDayNumber(week.monday)} – {formatDayNumber(week.monday + 6)}
                </span>
              )}
              <button
                type="button"
                className="button button-soft traffic-week-turn"
                aria-label="Следующая неделя"
                disabled={weekIndex >= weeks.length - 1}
                onClick={() => turnWeek(1)}
              >
                <Icon name="chevronRight" />
              </button>
            </div>
            <div className="traffic-week-total end">
              <span>Выручка по факту</span>
              <strong>
                {formatRubles(revenue?.fact ?? null)}
                {weekDeviation !== null && (
                  <>
                    {" "}
                    <span className={deviationClass(weekDeviation)}>
                      {formatDeviation(weekDeviation)}
                    </span>
                  </>
                )}
              </strong>
            </div>
          </div>
          <div className="traffic-days">
            {week?.days.map((next, weekday) =>
              next ? (
                <DayTile
                  key={next.day}
                  day={next}
                  name={dayName(next)}
                  past={today !== null && dayNumber(next.day) < dayNumber(today)}
                  active={next.day === day.day}
                  onSelect={() => setSelected(next.day)}
                />
              ) : (
                <div key={weekday} className="traffic-day-gap" aria-hidden="true">
                  {WEEKDAYS_SHORT[weekday]}
                </div>
              ),
            )}
          </div>
          {day.receipts === null || day.revenue === null ? (
            <p className="list-empty">По этому дню недели за выбранный период данных нет</p>
          ) : (
            <>
              {fact && (
                <dl className="traffic-results">
                  <DayResult
                    title={`Покупатели ${measured}`}
                    fact={fact.receipts}
                    plan={fact.plan_receipts}
                    format={formatPeople}
                  />
                  <DayResult
                    title={`Выручка ${measured}`}
                    fact={Number(fact.revenue)}
                    plan={fact.plan_revenue}
                    format={formatRubles}
                  />
                </dl>
              )}
              <p className="traffic-note">
                {WEEKDAYS[day.weekday]}, {formatDate(day.day)}: обычно{" "}
                {formatPeople(day.receipts.low)}–{formatPeople(day.receipts.high)} покупателей и{" "}
                {formatRubles(day.revenue.low)}–{formatRubles(day.revenue.high)} выручки. По{" "}
                {day.based_on}{" "}
                {plural(day.based_on, "прошлому дню", "прошлым дням", "прошлым дням")} с{" "}
                {formatDate(forecast.date_from)}.
                {day.based_on < RELIABLE_DAYS && " Мало данных, прогноз примерный."} Прогноз не
                учитывает праздники.
              </p>
              <div className="traffic-pair">
                <div>
                  <h3 className="traffic-subtitle">Покупатели по часам</h3>
                  <ForecastChart
                    key={day.day}
                    hours={day.hours.map(({ hour, receipts, fact_receipts }) => ({
                      hour,
                      value: receipts,
                      fact: fact_receipts,
                    }))}
                    label={`Прогноз и факт покупателей по часам на ${formatDate(day.day)}`}
                    legend="Ожидается покупателей"
                    format={formatPeople}
                  />
                </div>
                <div>
                  <h3 className="traffic-subtitle">Выручка по часам</h3>
                  <ForecastChart
                    key={day.day}
                    hours={day.hours.map(({ hour, revenue, fact_revenue }) => ({
                      hour,
                      value: revenue,
                      fact: fact_revenue === null ? null : Number(fact_revenue),
                    }))}
                    label={`Прогноз и факт выручки по часам на ${formatDate(day.day)}`}
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
