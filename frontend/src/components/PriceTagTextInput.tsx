import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";

import type { PriceTagTextLayout } from "../types";

interface Props extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  layout: PriceTagTextLayout | undefined;
  subtitle?: boolean;
}

export default function PriceTagTextInput({ layout, subtitle = false, className = "", ...props }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const input = ref.current;
    if (!input) {
      return;
    }
    function resize() {
      if (input) {
        input.style.height = "0px";
        input.style.height = `${input.scrollHeight - 16}px`;
      }
    }
    resize();
    const observer = new ResizeObserver(resize);
    if (input.parentElement) {
      observer.observe(input.parentElement);
    }
    let current = true;
    void document.fonts.ready.then(() => current && resize());
    return () => {
      current = false;
      observer.disconnect();
    };
  }, [props.value, layout]);

  return (
    <textarea
      {...props}
      ref={ref}
      rows={2}
      maxLength={200}
      spellCheck={false}
      className={`cell price-tag-live-text${subtitle ? " price-tag-live-subtitle" : ""} ${className}`}
      style={
        layout
          ? {
              width: `${layout.width}pt`,
              fontSize: `${layout.font_size}pt`,
              lineHeight: layout.leading,
            }
          : undefined
      }
    />
  );
}
