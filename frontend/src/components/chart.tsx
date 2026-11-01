import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";

export const CHART_HEIGHT = 240;
export const MARGIN = { top: 16, right: 8, bottom: 26, left: 40 };
const AXIS_LABEL_WIDTH = 44;

// the drawing follows the real width, a stretched viewBox would stretch the text too
export function useWidth<Element extends HTMLElement>(): [RefObject<Element | null>, number] {
  const ref = useRef<Element>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      setWidth(entry?.contentRect.width ?? 0);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

// the mark under the pointer or the keyboard, the arrow keys walk along the axis
export function useActive(count: number) {
  const [active, setActive] = useState<number | null>(null);

  function onKeyDown(event: KeyboardEvent) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step !== 0 && count > 0) {
      event.preventDefault();
      const next = active === null ? 0 : active + step;
      setActive(Math.min(Math.max(next, 0), count - 1));
    }
  }

  return { active, setActive, onKeyDown };
}

// round steps for the axis, from zero to above the largest value
export function niceTicks(max: number): number[] {
  const rough = Math.max(max, 1) / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((factor) => factor * power).find((value) => value >= rough)!;
  const whole = Math.max(step, 1);
  const ticks = [];
  for (let tick = 0; tick < max + whole; tick += whole) {
    ticks.push(tick);
  }
  return ticks;
}

// a column, rounded at the data end and square at the baseline
export function columnPath(x: number, y: number, width: number, height: number): string {
  const radius = Math.min(4, width / 2, height);
  const bottom = y + height;
  return (
    `M${x} ${bottom}V${y + radius}Q${x} ${y} ${x + radius} ${y}` +
    `H${x + width - radius}Q${x + width} ${y} ${x + width} ${y + radius}V${bottom}Z`
  );
}

interface GridProps {
  ticks: number[];
  y: (value: number) => number;
  width: number;
  format?: (tick: number) => string;
}

export function ChartGrid({ ticks, y, width, format }: GridProps) {
  return (
    <g>
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            className="chart-grid"
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={y(tick)}
            y2={y(tick)}
          />
          <text className="chart-axis" x={MARGIN.left - 8} y={y(tick) + 4} textAnchor="end">
            {format ? format(tick) : tick.toLocaleString("ru-RU")}
          </text>
        </g>
      ))}
    </g>
  );
}

interface LabelsProps {
  labels: { key: string | number; x: number; text: string }[];
  plotWidth: number;
}

// as many labels as fit, the rest stay in the tooltip
export function ChartLabels({ labels, plotWidth }: LabelsProps) {
  const every = Math.max(Math.ceil((labels.length * AXIS_LABEL_WIDTH) / Math.max(plotWidth, 1)), 1);
  return (
    <g>
      {labels
        .filter((_, index) => index % every === 0)
        .map((label) => (
          <text
            key={label.key}
            className="chart-axis"
            x={label.x}
            y={CHART_HEIGHT - 8}
            textAnchor="middle"
          >
            {label.text}
          </text>
        ))}
    </g>
  );
}

interface TooltipProps {
  x: number;
  y: number;
  width: number;
  children: ReactNode;
}

export function ChartTooltip({ x, y, width, children }: TooltipProps) {
  // kept inside the chart, the sheets around it clip
  const side = 80;
  const left = width > side * 2 ? Math.min(Math.max(x, side), width - side) : width / 2;
  return (
    <div className="chart-tooltip" style={{ left, top: y }} role="status">
      {children}
    </div>
  );
}

interface LegendProps {
  items: { key: string; label: string; mark: "line" | "bar" | "band" }[];
}

export function ChartLegend({ items }: LegendProps) {
  return (
    <ul className="chart-legend">
      {items.map((item) => (
        <li key={item.key}>
          <span className={`chart-key chart-key-${item.mark}`} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
