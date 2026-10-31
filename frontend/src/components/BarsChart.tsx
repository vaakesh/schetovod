import {
  CHART_HEIGHT,
  ChartGrid,
  ChartLabels,
  ChartTooltip,
  MARGIN,
  columnPath,
  niceTicks,
  useActive,
  useWidth,
} from "./chart";

const MAX_BAR = 24;
const MIN_GAP = 2;

export interface Bar {
  key: string | number;
  axis: string;
  title: string;
  value: number | null;
  shown: string;
  detail?: string;
}

interface Props {
  bars: Bar[];
  label: string;
}

export default function BarsChart({ bars, label }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const { active, setActive } = useActive(bars.length);

  const plotWidth = width - MARGIN.left - MARGIN.right;
  const slot = plotWidth / Math.max(bars.length, 1);
  const barWidth = Math.max(Math.min(slot - MIN_GAP, MAX_BAR), 1);
  const baseline = CHART_HEIGHT - MARGIN.bottom;
  const ticks = niceTicks(Math.max(...bars.map((bar) => bar.value ?? 0), 0));
  const top = ticks[ticks.length - 1] ?? 1;
  const y = (value: number) =>
    baseline - (value / Math.max(top, 1)) * (baseline - MARGIN.top);
  const center = (index: number) => MARGIN.left + slot * (index + 0.5);
  const shown = active === null ? undefined : bars[active];

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={CHART_HEIGHT} role="img" aria-label={label}>
          <ChartGrid ticks={ticks} y={y} width={width} />
          <ChartLabels
            plotWidth={plotWidth}
            labels={bars.map((bar, index) => ({
              key: bar.key,
              x: center(index),
              text: bar.axis,
            }))}
          />
          {bars.map((bar, index) => {
            const value = bar.value ?? 0;
            return (
              <g key={bar.key}>
                {value > 0 && (
                  <path
                    className={active === index ? "chart-bar active" : "chart-bar"}
                    d={columnPath(center(index) - barWidth / 2, y(value), barWidth, baseline - y(value))}
                  />
                )}
                {/* the whole column reacts, a low bar is too small to aim at */}
                <rect
                  className="chart-hit"
                  x={center(index) - slot / 2}
                  y={MARGIN.top}
                  width={slot}
                  height={baseline - MARGIN.top}
                  tabIndex={0}
                  aria-label={`${bar.title}: ${bar.shown}`}
                  onPointerEnter={() => setActive(index)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                />
              </g>
            );
          })}
        </svg>
      )}
      {shown && active !== null && (
        <ChartTooltip x={center(active)} y={y(shown.value ?? 0)} width={width}>
          <strong>{shown.shown}</strong>
          <span>{shown.title}</span>
          {shown.detail && <span>{shown.detail}</span>}
        </ChartTooltip>
      )}
    </div>
  );
}
