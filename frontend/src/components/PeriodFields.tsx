interface Props {
  start: string;
  end: string;
  onStart: (value: string) => void;
  onEnd: (value: string) => void;
}

export default function PeriodFields({ start, end, onStart, onEnd }: Props) {
  return (
    <div className="report-period">
      <label className="field">
        <span className="field-label">С</span>
        <input
          className="input"
          type="date"
          value={start}
          max={end}
          onChange={(event) => onStart(event.target.value)}
        />
      </label>
      <label className="field">
        <span className="field-label">По</span>
        <input
          className="input"
          type="date"
          value={end}
          min={start}
          onChange={(event) => onEnd(event.target.value)}
        />
      </label>
    </div>
  );
}
