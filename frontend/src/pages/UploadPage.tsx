import { useRef, useState } from "react";

import { MAX_SLOTS, type BatchUpload } from "../batch";
import DropPage from "../components/DropPage";
import Icon from "../components/icons";
import InvoiceSlot from "../components/InvoiceSlot";
import PageHead from "../components/PageHead";
import type { Route } from "../router";

interface Props {
  batch: BatchUpload;
  go: (route: Route) => void;
}

export default function UploadPage({ batch, go }: Props) {
  const input = useRef<HTMLInputElement>(null);
  // the slot the open file picker fills, null for a new one
  const target = useRef<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Safari opens a file picker only from the click itself, not after a render
  function pick(id: number | null) {
    target.current = id;
    input.current?.click();
  }

  function add(id: number | null, files: File[]) {
    setError(batch.addFiles(id, files));
  }

  return (
    <DropPage
      className="page"
      busy={false}
      onJson={() => setError("Здесь нужны фото накладной, JSON загружается в разделе Накладные")}
      onImages={(files) => add(null, files)}
      onRefused={setError}
    >
      <PageHead
        title="Загрузка накладных"
        meta={`У каждой накладной свой контейнер с её фото, до ${MAX_SLOTS} накладных за раз`}
      >
        {batch.done > 0 && (
          <button type="button" className="button button-ghost" onClick={batch.clearDone}>
            Убрать готовые
          </button>
        )}
        <button
          type="button"
          className="button button-primary button-icon"
          disabled={batch.filled === 0}
          onClick={batch.start}
        >
          <Icon name="upload" size={18} />
          Распознать{batch.filled > 0 ? ` (${batch.filled})` : ""}
        </button>
      </PageHead>

      <input
        ref={input}
        type="file"
        // image/* lets a tablet offer the gallery and the camera
        accept="image/*"
        multiple
        hidden
        onChange={(event) => {
          // photos picked together are the pages of one invoice
          const files = Array.from(event.target.files ?? []);
          if (files.length > 0) {
            add(target.current, files);
          }
          // reset so that the same file can be picked again
          event.target.value = "";
        }}
      />

      {error && (
        <div className="alert list-alert">
          <pre>{error}</pre>
        </div>
      )}

      <div className="slots">
        {batch.slots.map((slot, index) => (
          <InvoiceSlot
            key={slot.id}
            slot={slot}
            number={index + 1}
            onPick={() => pick(slot.id)}
            onRemoveFile={(file) => batch.removeFile(slot.id, file)}
            onRemove={() => batch.removeSlot(slot.id)}
            onRetry={() => batch.retry(slot.id)}
            onOpen={(id) => go({ page: "draft", id })}
          />
        ))}
        {batch.slots.length < MAX_SLOTS && (
          <button type="button" className="slot-new" onClick={() => pick(null)}>
            <Icon name="plus" size={24} />
            Новая накладная
          </button>
        )}
      </div>
    </DropPage>
  );
}
