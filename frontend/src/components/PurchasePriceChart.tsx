import { useState, type MouseEvent } from "react";

import { formatDate, formatNumber } from "../format";
import { dayNumber, formatDayNumber, formatThousands } from "../traffic";
import type { PurchaseLine } from "../types";
import { CHART_HEIGHT, ChartGrid, ChartLabels, ChartTooltip, MARGIN, niceTicks, useWidth } from "./chart";

interface Props {
  lines: PurchaseLine[];
  selected: number;
  onSelect: (index: number) => void;
}

export default function PurchasePriceChart({ lines, selected, onSelect }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [retail, setRetail] = useState(false);
  const [inspected, setInspected] = useState<"cost" | "retail" | null>(null);
  const points = lines.map((line) => ({
    day: dayNumber(line.occurred_on), cost: Number(line.cost_price), retail: Number(line.retail_price),
  }));
  const first = points[0]!.day;
  const last = points[points.length - 1]!.day;
  const plot = Math.max(width - MARGIN.left - 24, 1);
  const baseline = CHART_HEIGHT - MARGIN.bottom;
  const x = (day: number) => MARGIN.left + plot * (last === first ? 0.5 : (day - first) / (last - first));
  let min = Infinity;
  let max = 0;
  for (const point of points) {
    min = Math.min(min, point.cost, retail ? point.retail : point.cost);
    max = Math.max(max, point.cost, retail ? point.retail : point.cost);
  }
  const span = Math.max(max - min, max * 0.05, 0.04);
  const step = (niceTicks(span * 100)[1] ?? 1) / 100;
  const low = Math.max(0, (Math.ceil(min / step) - 1) * step);
  const high = (Math.floor(max / step) + 1) * step;
  const ticks = Array.from({ length: Math.round((high - low) / step) + 1 }, (_, i) => Number((low + i * step).toFixed(2)));
  const y = (price: number) => baseline - (price - low) / (high - low) * (baseline - MARGIN.top);
  const labels = [first, ...(last > first ? [last] : [])].map((day) => ({
    key: day, x: x(day), text: formatDayNumber(day),
  }));

  function pick(event: MouseEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const pointerX = event.clientX - box.left;
    const pointerY = event.clientY - box.top;
    let distance = Infinity;
    let vertical = Infinity;
    let nearest = 0;
    let nearMarker: number | null = null;
    let markerDistance = 22;
    points.forEach((point, index) => {
      const dx = Math.abs(x(point.day) - pointerX);
      const dy = Math.min(Math.abs(y(point.cost) - pointerY), retail ? Math.abs(y(point.retail) - pointerY) : Infinity);
      const radius = Math.hypot(dx, dy);
      if (radius < markerDistance) {
        nearMarker = index;
        markerDistance = radius;
      }
      if (dx < distance || (dx === distance && dy < vertical)) {
        distance = dx;
        vertical = dy;
        nearest = index;
      }
    });
    const index = nearMarker ?? nearest;
    const point = points[index]!;
    const retailCloser = retail && Math.abs(y(point.retail) - pointerY) < Math.abs(y(point.cost) - pointerY);
    setInspected(retailCloser ? "retail" : "cost");
    onSelect(index);
  }
  const active = points[selected]!;
  function series(field: "cost" | "retail") {
    return <g className={`purchase-series series-${field}`}>
      <polyline points={points.map((p) => `${x(p.day)},${y(p[field])}`).join(" ")} />
      {points.map((p, i) => <circle key={i} cx={x(p.day)} cy={y(p[field])} r={i === selected ? 5 : 3} />)}
    </g>;
  }
  return (
    <div className="chart purchase-chart" ref={ref}>
      <div className="purchase-chart-head">
        <h3 className="traffic-title">Цены поставок <small>₽/{lines[0]!.unit}</small></h3>
        <div className="purchase-legend"><span>Закупочная</span>
          <label><input type="checkbox" checked={retail} onChange={(e) => setRetail(e.target.checked)} /> Розничная</label>
        </div>
      </div>
      {width > MARGIN.left && <div className="purchase-plot">
        <svg width={width} height={CHART_HEIGHT} tabIndex={0}
          role="group" aria-label="Цены по поставкам. Стрелки влево и вправо выбирают поставку"
          onClick={pick} onBlur={() => setInspected(null)} onKeyDown={(e) => {
            if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
            e.preventDefault();
            setInspected("cost");
            onSelect(Math.max(0, Math.min(selected + (e.key === "ArrowLeft" ? -1 : 1), points.length - 1)));
          }}>
          <ChartGrid width={width} y={y} ticks={ticks} format={(tick) => tick >= 1000 ? formatThousands(tick) : tick.toLocaleString("ru-RU")} />
          <ChartLabels labels={labels} plotWidth={plot} />
          <line className="chart-crosshair" x1={x(active.day)} x2={x(active.day)} y1={MARGIN.top} y2={baseline} />
          {series("cost")}{retail && series("retail")}
        </svg>
        {inspected && (inspected === "cost" || retail) && <div aria-hidden="true" data-below={y(active[inspected]) < 72}>
          <ChartTooltip x={x(active.day)} y={y(active[inspected])} width={width}>
            <strong>{inspected === "cost" ? "Закупка" : "Розница"} {formatNumber(active[inspected])} ₽</strong>
            <span>{formatDate(lines[selected]!.occurred_on)} · {formatNumber(lines[selected]!.quantity)} {lines[selected]!.unit}</span>
          </ChartTooltip>
        </div>}
      </div>}
    </div>
  );
}
