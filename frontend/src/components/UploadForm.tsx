import { useRef, useState } from "react";

export type UploadKind = "json" | "image";

interface Props {
  kind: UploadKind;
  // which upload is running, both areas wait for it
  uploading: UploadKind | null;
  // a button in the top bar instead of the drop area
  compact?: boolean;
  // a low drop area above the invoice list
  slim?: boolean;
  onFiles: (files: File[]) => void;
}

const LABELS: Record<UploadKind, { title: string; button: string; hint: string; loading: string }> = {
  json: {
    title: "JSON-файл",
    button: "JSON",
    hint: "Перетащите JSON или выберите файл",
    loading: "Читаем накладную…",
  },
  image: {
    title: "Изображение",
    button: "Фото",
    hint: "Перетащите фото или выберите из галереи",
    loading: "Распознаём накладную, это может занять несколько минут…",
  },
};

function Icon({ kind }: { kind: UploadKind }) {
  if (kind === "image") {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="9" cy="10" r="1.8" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="m4 18 5-5 4 4 3-3 4 4" fill="none" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 16V5M7 10l5-5 5 5M5 19h14" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export default function UploadForm({ kind, uploading, compact = false, slim = false, onFiles }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const busy = uploading !== null;
  const loading = uploading === kind;
  const labels = LABELS[kind];

  // a json invoice is one file, photos are the pages of one invoice
  function take(list: FileList | null | undefined) {
    const files = Array.from(list ?? []);
    if (files.length > 0 && !busy) {
      onFiles(kind === "json" ? files.slice(0, 1) : files);
    }
  }

  const picker = (
    <input
      ref={input}
      type="file"
      // image/* lets a phone offer the gallery and the camera
      accept={kind === "json" ? ".json,application/json" : "image/*"}
      multiple={kind === "image"}
      hidden
      disabled={busy}
      onChange={(event) => {
        const files = event.target.files;
        take(files);
        // reset so that the same file can be uploaded again
        event.target.value = "";
      }}
    />
  );

  if (compact) {
    return (
      <>
        {picker}
        <button
          type="button"
          className="button button-ghost"
          disabled={busy}
          title={labels.hint}
          onClick={() => input.current?.click()}
        >
          {loading ? <span className="spinner" /> : labels.button}
        </button>
      </>
    );
  }

  return (
    <section
      className={["dropzone", slim && "dropzone-slim", dragging && "dragging", busy && !loading && "dropzone-idle"]
        .filter(Boolean)
        .join(" ")}
      role="button"
      tabIndex={busy ? -1 : 0}
      aria-label={`${labels.title}: ${labels.hint}`}
      aria-busy={loading}
      onClick={() => !busy && input.current?.click()}
      onKeyDown={(event) => {
        if (!busy && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          input.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        take(event.dataTransfer.files);
      }}
    >
      {picker}
      <span className="dropzone-icon">{loading ? <span className="spinner" /> : <Icon kind={kind} />}</span>
      <span className="dropzone-body">
        <span className="dropzone-title">{labels.title}</span>
        <span className="dropzone-text">{loading ? labels.loading : labels.hint}</span>
      </span>
    </section>
  );
}
