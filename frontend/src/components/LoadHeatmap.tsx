import { useState } from "react";

import { WEEKDAYS, WEEKDAYS_SHORT, formatCount, hourRange } from "../traffic";
import type { HeatCell } from "../types";
import { ChartTooltip, useWidth } from "./chart";

// the faintest step that still stands out from an empty cell
const MIN_SHARE = 8;

interface Props {
  cells: HeatCell[];
}

interface Hovered {
  cell: HeatCell;
  x: number;
  y: number;
}

function shade(value: number, max: number): string {
  if (value === 0) {
    return "var(--hover)";
  }
  const share = Math.round(MIN_SHARE + (value / max) * (100 - MIN_SHARE));
  return `color-mix(in oklab, var(--accent) ${share}%, var(--surface))`;
}

export default function LoadHeatmap({ cells }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hovered, setHovered] = useState<Hovered | null>(null);

  const hours = [...new Set(cells.map((cell) => cell.hour))];
  const weekdays = [...new Set(cells.map((cell) => cell.weekday))];
  const max = Math.max(...cells.map((cell) => cell.receipts), 1);

  function point(element: HTMLElement, cell: HeatCell) {
    setHovered({
      cell,
      x: element.offsetLeft + element.offsetWidth / 2,
      y: element.offsetTop,
    });
  }

  return (
    <div className="chart" ref={ref}>
      <div
        className="heatmap"
        style={{ gridTemplateColumns: `28px repeat(${hours.length}, minmax(0, 1fr))` }}
      >
        <span />
        {hours.map((hour) => (
          <span key={hour} className="heatmap-hour">
            {hour}
          </span>
        ))}
        {weekdays.map((weekday) => (
          <div key={weekday} className="heatmap-row">
            <span className="heatmap-day">{WEEKDAYS_SHORT[weekday]}</span>
            {cells
              .filter((cell) => cell.weekday === weekday)
              .map((cell) => (
                <div
                  key={cell.hour}
                  className="heatmap-cell"
                  style={{ background: shade(cell.receipts, max) }}
                  tabIndex={0}
                  aria-label={`${WEEKDAYS[weekday]}, ${hourRange(cell.hour)}: ${formatCount(cell.receipts)}`}
                  onPointerEnter={(event) => point(event.currentTarget, cell)}
                  onPointerLeave={() => setHovered(null)}
                  onFocus={(event) => point(event.currentTarget, cell)}
                  onBlur={() => setHovered(null)}
                />
              ))}
          </div>
        ))}
      </div>
      <div className="heatmap-scale">
        <span>0</span>
        <span className="heatmap-ramp" aria-hidden="true" />
        <span>{formatCount(max)} в час</span>
      </div>
      {hovered && (
        <ChartTooltip x={hovered.x} y={hovered.y} width={width}>
          <strong>{formatCount(hovered.cell.receipts)}</strong>
          <span>{WEEKDAYS[hovered.cell.weekday]}</span>
          <span>{hourRange(hovered.cell.hour)}</span>
        </ChartTooltip>
      )}
      <details className="heatmap-table">
        <summary>Показать таблицей</summary>
        <div className="table-wrap">
          <table className="list">
            <thead>
              <tr>
                <th />
                {hours.map((hour) => (
                  <th key={hour} className="num">
                    {hour}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {weekdays.map((weekday) => (
                <tr key={weekday}>
                  <td>{WEEKDAYS_SHORT[weekday]}</td>
                  {cells
                    .filter((cell) => cell.weekday === weekday)
                    .map((cell) => (
                      <td key={cell.hour} className="num">
                        {formatCount(cell.receipts)}
                      </td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
