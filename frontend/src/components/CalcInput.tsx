import { calculate, isExpression } from "../calc";

interface Props {
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
}

// the expression gives way to its sum, a broken one stays to be fixed
function counted(text: string): string {
  return calculate(text)?.replace(".", ",") ?? text;
}

// a money field that also counts: 3*225 + 3*95 and = leave 960 in it, so does leaving the field
export default function CalcInput({ value, onChange, autoFocus }: Props) {
  return (
    <input
      className="input input-money"
      // the decimal pad of a phone has no operators
      inputMode="text"
      autoComplete="off"
      autoCorrect="off"
      spellCheck={false}
      autoFocus={autoFocus}
      placeholder="0,00"
      value={value}
      onChange={(event) => {
        const text = event.target.value;
        const [expression = ""] = text.split("=");
        onChange(text.includes("=") ? counted(expression) : text);
      }}
      onKeyDown={(event) => {
        // the first enter shows the sum, the second one sends the form
        if (event.key === "Enter" && isExpression(value)) {
          event.preventDefault();
          onChange(counted(value));
        }
      }}
      onBlur={() => {
        if (isExpression(value)) {
          onChange(counted(value));
        }
      }}
    />
  );
}
