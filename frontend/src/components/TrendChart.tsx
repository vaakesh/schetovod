import type { PointerEvent } from "react";

import { formatDate } from "../format";
import { dayNumber, formatCount, formatRubles } from "../traffic";
import type { DayLoad } from "../types";
import {
  CHART_HEIGHT,
  ChartGrid,
  ChartLabels,
  ChartLegend,
  ChartTooltip,
  MARGIN,
  columnPath,
  niceTicks,
  useActive,
  useWidth,
} from "./chart";

const MAX_BAR = 24;
const MIN_GAP = 2;

interface Props {
  days: DayLoad[];
}

export default function TrendChart({ days }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const { active, setActive, onKeyDown } = useActive(days.length);

  const first = dayNumber(days[0]?.day ?? "01-01-2000");
  const last = dayNumber(days[days.length - 1]?.day ?? "01-01-2000");
  const plotWidth = width - MARGIN.left - MARGIN.right;
  // the calendar is the axis, a day off stays a gap
  const slot = plotWidth / (last - first + 1);
  const barWidth = Math.max(Math.min(slot - MIN_GAP, MAX_BAR), 1);
  const baseline = CHART_HEIGHT - MARGIN.bottom;
  const ticks = niceTicks(Math.max(...days.map((day) => day.receipts), 0));
  const top = ticks[ticks.length - 1] ?? 1;
  const y = (value: number) =>
    baseline - (value / Math.max(top, 1)) * (baseline - MARGIN.top);
  const x = (day: DayLoad) => MARGIN.left + slot * (dayNumber(day.day) - first + 0.5);

  const trend = days.filter((day) => day.trend !== null);
  const shown = active === null ? undefined : days[active];

  function follow(event: PointerEvent<SVGSVGElement>) {
    const left = event.currentTarget.getBoundingClientRect().left;
    const pointer = event.clientX - left;
    let nearest = 0;
    days.forEach((day, index) => {
      if (Math.abs(x(day) - pointer) < Math.abs(x(days[nearest]!) - pointer)) {
        nearest = index;
      }
    });
    setActive(nearest);
  }

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg
          width={width}
          height={CHART_HEIGHT}
          role="img"
          aria-label="Покупатели по дням и среднее за 7 дней"
          tabIndex={0}
          onPointerMove={follow}
          onPointerLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
          onKeyDown={onKeyDown}
        >
          <ChartGrid ticks={ticks} y={y} width={width} />
          <ChartLabels
            plotWidth={plotWidth}
            labels={days.map((day) => ({
              key: day.day,
              x: x(day),
              text: day.day.slice(0, 5).replace("-", "."),
            }))}
          />
          {days.map((day, index) => (
            <path
              key={day.day}
              className={active === index ? "chart-bar-quiet active" : "chart-bar-quiet"}
              d={columnPath(x(day) - barWidth / 2, y(day.receipts), barWidth, baseline - y(day.receipts))}
            />
          ))}
          {trend.length > 1 && (
            <path
              className="chart-line"
              d={`M${trend.map((day) => `${x(day)} ${y(day.trend ?? 0)}`).join("L")}`}
            />
          )}
          {shown && <line className="chart-crosshair" x1={x(shown)} x2={x(shown)} y1={MARGIN.top} y2={baseline} />}
        </svg>
      )}
      <ChartLegend
        items={[
          { key: "day", label: "Покупателей за день", mark: "bar" },
          { key: "trend", label: "Среднее за 7 дней", mark: "line" },
        ]}
      />
      {shown && (
        <ChartTooltip x={x(shown)} y={y(shown.receipts)} width={width}>
          <strong>{formatCount(shown.receipts)}</strong>
          <span>{formatDate(shown.day)}</span>
          {shown.trend !== null && <span>среднее {formatCount(shown.trend)}</span>}
          <span>выручка {formatRubles(shown.revenue)}</span>
        </ChartTooltip>
      )}
    </div>
  );
}
