import { useEffect, useRef, useState } from "react";

import Icon from "./icons";

export type UploadKind = "json" | "image" | "manual";

export const UPLOAD_LOADING: Record<UploadKind, string> = {
  json: "Читаем накладную…",
  image: "Распознаём накладную, это может занять несколько минут…",
  manual: "Создаём накладную…",
};

interface Props {
  // which upload is running, the button waits for it
  uploading: UploadKind | null;
  onJson: (files: File[]) => void;
  onImages: (files: File[]) => void;
  onBatch: () => void;
  onManual: () => void;
}

export default function UploadMenu({ uploading, onJson, onImages, onBatch, onManual }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const jsonInput = useRef<HTMLInputElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const busy = uploading !== null;

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointer(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Safari opens a file picker only from the click itself, not after a render
  function pick(input: HTMLInputElement | null) {
    input?.click();
    setOpen(false);
  }

  return (
    <div className="upload-menu" ref={root}>
      {/* outside the menu, closing it must not drop an open file picker */}
      <input
        ref={jsonInput}
        type="file"
        accept=".json,application/json"
        hidden
        disabled={busy}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length > 0) {
            // a json invoice is one file
            onJson(files.slice(0, 1));
          }
          // reset so that the same file can be uploaded again
          event.target.value = "";
        }}
      />
      <input
        ref={imageInput}
        type="file"
        // image/* lets a tablet offer the gallery and the camera
        accept="image/*"
        multiple
        hidden
        disabled={busy}
        onChange={(event) => {
          // photos are the pages of one invoice
          const files = Array.from(event.target.files ?? []);
          if (files.length > 0) {
            onImages(files);
          }
          event.target.value = "";
        }}
      />
      <button
        ref={trigger}
        type="button"
        className="button button-primary button-icon"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        onClick={() => setOpen(!open)}
      >
        {busy ? <span className="spinner" /> : <Icon name="upload" size={18} />}
        Загрузить накладную
      </button>
      {open && (
        <div className="menu upload-options" role="menu">
          <button
            type="button"
            className="menu-item upload-option"
            role="menuitem"
            autoFocus
            onClick={() => pick(imageInput.current)}
          >
            <Icon name="photo" />
            <span>
              <span className="menu-title">Фото накладной</span>
              <span className="menu-meta">Камера, галерея или файлы, можно несколько страниц</span>
            </span>
          </button>
          <button
            type="button"
            className="menu-item upload-option"
            role="menuitem"
            onClick={onBatch}
          >
            <Icon name="invoices" />
            <span>
              <span className="menu-title">Несколько накладных</span>
              <span className="menu-meta">До 10 сразу, у каждой свой контейнер с фото</span>
            </span>
          </button>
          <button
            type="button"
            className="menu-item upload-option"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onManual();
            }}
          >
            <Icon name="plus" />
            <span>
              <span className="menu-title">Вручную</span>
              <span className="menu-meta">Пустая накладная, нужные строки вносите сами</span>
            </span>
          </button>
          <button
            type="button"
            className="menu-item upload-option"
            role="menuitem"
            onClick={() => pick(jsonInput.current)}
          >
            <Icon name="file" />
            <span>
              <span className="menu-title">JSON-файл</span>
              <span className="menu-meta">Готовая накладная, без распознавания</span>
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
