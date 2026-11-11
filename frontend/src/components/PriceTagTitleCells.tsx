import type { FocusEvent, KeyboardEvent } from "react";

import type { FormRow } from "../priceTags";
import PriceTagPreview, { usePriceTagPreview } from "./PriceTagPreview";
import PriceTagTextInput from "./PriceTagTextInput";

interface Props {
  row: FormRow;
  invalid: boolean;
  onChange: (change: Partial<FormRow>) => void;
  onFocus: (event: FocusEvent<HTMLTextAreaElement>) => void;
  onBlur: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}

export default function PriceTagTitleCells({ row, invalid, onChange, onFocus, onBlur, onKeyDown }: Props) {
  const preview = usePriceTagPreview(row);

  return (
    <>
      <td className="price-tag-name">
        <PriceTagTextInput
          layout={preview.layout?.name}
          className={invalid ? "cell-required" : ""}
          aria-label="Название"
          aria-describedby="price-tags-text-help"
          placeholder="Товар и марка"
          value={row.name}
          onFocus={onFocus}
          onBlur={onBlur}
          onKeyDown={onKeyDown}
          onChange={(event) => onChange({ name: event.target.value })}
        />
      </td>
      <td className="price-tag-subtitle-cell">
        <PriceTagTextInput
          layout={preview.layout?.subtitle}
          subtitle
          aria-label="Подназвание"
          aria-describedby="price-tags-text-help"
          placeholder="Жирность, вкус, сорт"
          value={row.subtitle}
          onChange={(event) => onChange({ subtitle: event.target.value })}
        />
      </td>
      <td className="price-tag-preview-cell">
        <PriceTagPreview row={row} preview={preview} />
      </td>
    </>
  );
}
