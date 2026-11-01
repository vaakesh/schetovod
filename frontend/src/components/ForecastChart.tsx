import type { PointerEvent } from "react";

import { hourRange } from "../traffic";
import type { ForecastValue } from "../types";
import {
  CHART_HEIGHT,
  ChartGrid,
  ChartLabels,
  ChartLegend,
  ChartTooltip,
  MARGIN,
  niceTicks,
  useActive,
  useWidth,
} from "./chart";

interface Props {
  hours: { hour: number; value: ForecastValue; fact: number | null }[];
  label: string;
  legend: string;
  format: (value: number) => string;
  formatTick?: (tick: number) => string;
}

export default function ForecastChart({ hours, label, legend, format, formatTick }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const { active, setActive, onKeyDown } = useActive(hours.length);

  const plotWidth = width - MARGIN.left - MARGIN.right;
  const slot = plotWidth / Math.max(hours.length, 1);
  const baseline = CHART_HEIGHT - MARGIN.bottom;
  const ticks = niceTicks(Math.max(...hours.map(({ value, fact }) => Math.max(value.high, fact ?? 0)), 0));
  const top = ticks[ticks.length - 1] ?? 1;
  // an hour of refunds goes below zero, the axis starts at zero
  const y = (value: number) =>
    baseline - (Math.max(value, 0) / Math.max(top, 1)) * (baseline - MARGIN.top);
  const x = (index: number) => MARGIN.left + slot * (index + 0.5);

  const upper = hours.map(({ value }, index) => `${x(index)} ${y(value.high)}`);
  const lower = hours.map(({ value }, index) => `${x(index)} ${y(value.low)}`).reverse();
  const middle = hours.map(({ value }, index) => `${x(index)} ${y(value.expected)}`);
  const facts = hours.flatMap(({ fact }, index) => (fact === null ? [] : [{ index, fact }]));
  const actual = facts.map(({ index, fact }) => `${x(index)} ${y(fact)}`);
  const shown = active === null ? undefined : hours[active];
  const shownFact = shown?.fact ?? null;

  function follow(event: PointerEvent<SVGSVGElement>) {
    const left = event.currentTarget.getBoundingClientRect().left;
    const index = Math.floor((event.clientX - left - MARGIN.left) / slot);
    setActive(Math.min(Math.max(index, 0), hours.length - 1));
  }

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg
          width={width}
          height={CHART_HEIGHT}
          role="img"
          aria-label={label}
          tabIndex={0}
          onPointerMove={follow}
          onPointerLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
          onKeyDown={onKeyDown}
        >
          <ChartGrid ticks={ticks} y={y} width={width} format={formatTick} />
          <ChartLabels
            plotWidth={plotWidth}
            labels={hours.map(({ hour }, index) => ({
              key: hour,
              x: x(index),
              text: `${hour}:00`,
            }))}
          />
          <path className="chart-band" d={`M${[...upper, ...lower].join("L")}Z`} />
          {shown && active !== null && (
            <line
              className="chart-crosshair"
              x1={x(active)}
              x2={x(active)}
              y1={MARGIN.top}
              y2={baseline}
            />
          )}
          <path className="chart-line" d={`M${middle.join("L")}`} />
          {actual.length > 1 && <path className="chart-line-fact" d={`M${actual.join("L")}`} />}
          {/* a line of one point draws nothing */}
          {facts.length === 1 && facts[0] && (
            <circle className="chart-dot-fact" cx={x(facts[0].index)} cy={y(facts[0].fact)} r={5} />
          )}
          {shown && active !== null && (
            <circle className="chart-dot" cx={x(active)} cy={y(shown.value.expected)} r={5} />
          )}
          {active !== null && shownFact !== null && (
            <circle className="chart-dot-fact" cx={x(active)} cy={y(shownFact)} r={5} />
          )}
        </svg>
      )}
      <ChartLegend
        items={[
          { key: "median", label: legend, mark: "line" },
          ...(facts.length > 0 ? [{ key: "fact", label: "По факту", mark: "fact" as const }] : []),
          { key: "spread", label: "Обычный разброс", mark: "band" },
        ]}
      />
      {shown && active !== null && (
        <ChartTooltip x={x(active)} y={y(Math.max(shown.value.high, shownFact ?? 0))} width={width}>
          <strong>{format(shown.value.expected)}</strong>
          <span>{hourRange(shown.hour)}</span>
          {shownFact !== null && <span>по факту {format(shownFact)}</span>}
          <span>
            обычно {format(shown.value.low)}–{format(shown.value.high)}
          </span>
        </ChartTooltip>
      )}
    </div>
  );
}
