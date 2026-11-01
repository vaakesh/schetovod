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
  hours: { hour: number; value: ForecastValue }[];
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
  const ticks = niceTicks(Math.max(...hours.map(({ value }) => value.high), 0));
  const top = ticks[ticks.length - 1] ?? 1;
  // an hour of refunds goes below zero, the axis starts at zero
  const y = (value: number) =>
    baseline - (Math.max(value, 0) / Math.max(top, 1)) * (baseline - MARGIN.top);
  const x = (index: number) => MARGIN.left + slot * (index + 0.5);

  const upper = hours.map(({ value }, index) => `${x(index)} ${y(value.high)}`);
  const lower = hours.map(({ value }, index) => `${x(index)} ${y(value.low)}`).reverse();
  const middle = hours.map(({ value }, index) => `${x(index)} ${y(value.expected)}`);
  const shown = active === null ? undefined : hours[active];

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
          {shown && active !== null && (
            <circle className="chart-dot" cx={x(active)} cy={y(shown.value.expected)} r={5} />
          )}
        </svg>
      )}
      <ChartLegend
        items={[
          { key: "median", label: legend, mark: "line" },
          { key: "spread", label: "Обычный разброс", mark: "band" },
        ]}
      />
      {shown && active !== null && (
        <ChartTooltip x={x(active)} y={y(shown.value.high)} width={width}>
          <strong>{format(shown.value.expected)}</strong>
          <span>{hourRange(shown.hour)}</span>
          <span>
            обычно {format(shown.value.low)}–{format(shown.value.high)}
          </span>
        </ChartTooltip>
      )}
    </div>
  );
}
