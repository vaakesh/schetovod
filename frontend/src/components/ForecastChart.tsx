import type { PointerEvent } from "react";

import { formatPeople, hourRange } from "../traffic";
import type { HourForecast } from "../types";
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
  hours: HourForecast[];
  label: string;
}

export default function ForecastChart({ hours, label }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const { active, setActive, onKeyDown } = useActive(hours.length);

  const plotWidth = width - MARGIN.left - MARGIN.right;
  const slot = plotWidth / Math.max(hours.length, 1);
  const baseline = CHART_HEIGHT - MARGIN.bottom;
  const ticks = niceTicks(Math.max(...hours.map((hour) => hour.high), 0));
  const top = ticks[ticks.length - 1] ?? 1;
  const y = (value: number) =>
    baseline - (value / Math.max(top, 1)) * (baseline - MARGIN.top);
  const x = (index: number) => MARGIN.left + slot * (index + 0.5);

  const upper = hours.map((hour, index) => `${x(index)} ${y(hour.high)}`);
  const lower = hours.map((hour, index) => `${x(index)} ${y(hour.low)}`).reverse();
  const middle = hours.map((hour, index) => `${x(index)} ${y(hour.receipts)}`);
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
          <ChartGrid ticks={ticks} y={y} width={width} />
          <ChartLabels
            plotWidth={plotWidth}
            labels={hours.map((hour, index) => ({
              key: hour.hour,
              x: x(index),
              text: `${hour.hour}:00`,
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
            <circle className="chart-dot" cx={x(active)} cy={y(shown.receipts)} r={5} />
          )}
        </svg>
      )}
      <ChartLegend
        items={[
          { key: "median", label: "Ожидается покупателей", mark: "line" },
          { key: "spread", label: "Обычный разброс", mark: "band" },
        ]}
      />
      {shown && active !== null && (
        <ChartTooltip x={x(active)} y={y(shown.high)} width={width}>
          <strong>{formatPeople(shown.receipts)}</strong>
          <span>{hourRange(shown.hour)}</span>
          <span>
            обычно {formatPeople(shown.low)}–{formatPeople(shown.high)}
          </span>
        </ChartTooltip>
      )}
    </div>
  );
}
