interface Props<T extends string> {
  value: T;
  options: Record<T, string>;
  label: string;
  onChange: (value: T) => void;
}

// two options side by side, like the boxes to tick on the paper form
export default function ToggleField<T extends string>({ value, options, label, onChange }: Props<T>) {
  return (
    <div className="price-tag-toggle" role="radiogroup" aria-label={label}>
      {(Object.keys(options) as T[]).map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={option === value}
          className={option === value ? "active" : undefined}
          onClick={() => onChange(option)}
        >
          {options[option]}
        </button>
      ))}
    </div>
  );
}
