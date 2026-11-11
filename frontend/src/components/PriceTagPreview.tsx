import { useEffect, useState } from "react";

import { previewPriceTag } from "../api";
import { message } from "../message";
import { previewFields, type FormRow } from "../priceTags";
import type { PriceTagFields, PriceTagPreview as Preview } from "../types";

interface PreviewState {
  request: string;
  result: Preview | null;
  error: string | null;
}

export function usePriceTagPreview(row: FormRow) {
  const request = JSON.stringify(previewFields(row));
  const [state, setState] = useState<PreviewState | null>(null);

  useEffect(() => {
    if (request === "null") {
      return;
    }
    let current = true;
    const timer = window.setTimeout(() => {
      previewPriceTag(JSON.parse(request) as PriceTagFields)
        .then((result) => current && setState({ request, result, error: null }))
        .catch((reason) => current && setState({ request, result: null, error: message(reason) }));
    }, 180);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [request]);

  const ready = request === state?.request;
  return {
    result: request !== "null" ? state?.result ?? null : null,
    layout: state?.result?.title,
    error: ready ? state.error : null,
    pending: request !== "null" && !ready,
  };
}

interface Props {
  row: FormRow;
  preview: ReturnType<typeof usePriceTagPreview>;
}

export default function PriceTagPreview({ row, preview }: Props) {
  const { result, error, pending } = preview;
  const [url, setUrl] = useState<{ svg: string; src: string } | null>(null);

  useEffect(() => {
    if (!result) {
      return;
    }
    const src = URL.createObjectURL(new Blob([result.svg], { type: "image/svg+xml" }));
    setUrl({ svg: result.svg, src });
    return () => URL.revokeObjectURL(src);
  }, [result]);

  const [width, height] = row.size.split("x").map(Number);
  const current = result && url?.svg === result.svg;

  return (
    <div className="price-tag-preview" aria-busy={pending}>
      {row.size ? (
        <>
          <div
            className="price-tag-preview-paper"
            style={{ width: `${width}mm`, aspectRatio: `${width} / ${height}` }}
          >
            {current && url && (
              <img
                src={url.src}
                alt={`Ценник ${width! / 10}×${height! / 10} см: ${row.name}${row.subtitle ? `, ${row.subtitle}` : ""}`}
              />
            )}
            {pending && <span className="price-tag-preview-status">Обновляем…</span>}
            {error && <span className="price-tag-preview-status">Нет предпросмотра</span>}
          </div>
          {error && (
            <p className="price-tag-preview-error" role="alert">{error}</p>
          )}
        </>
      ) : (
        <p className="price-tag-preview-hint">Выберите размер для предпросмотра</p>
      )}
    </div>
  );
}
