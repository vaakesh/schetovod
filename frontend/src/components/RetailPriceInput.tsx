import { useState, type InputHTMLAttributes } from "react";

import { toDecimal } from "../form";

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "onBlur" | "inputMode">;

interface Props extends InputProps {
  value: string | null;
  onChange: (price: string | null) => void;
}

export default function RetailPriceInput({ value, onChange, ...props }: Props) {
  // keep the typed separator while an autosave of the whole rubles is in flight
  const [text, setText] = useState<string | null>(null);
  return (
    <input
      {...props}
      inputMode="decimal"
      value={text ?? value?.replace(".", ",") ?? ""}
      onChange={(event) => {
        const next = event.target.value;
        if (next !== "" && !/^\d{1,12}(?:[.,]\d{0,2})?$/.test(next)) return;
        setText(next);
        const price = toDecimal(next.replace(/[.,]$/, ""));
        if (price !== value) onChange(price);
      }}
      onBlur={() => setText(null)}
    />
  );
}
