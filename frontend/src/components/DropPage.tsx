import { useState, type DragEvent, type ReactNode } from "react";

interface Props {
  className: string;
  // an upload is running, a new one has to wait
  busy: boolean;
  onJson: (files: File[]) => void;
  onImages: (files: File[]) => void;
  onRefused: (text: string) => void;
  children: ReactNode;
}

function isJson(file: File): boolean {
  return file.type === "application/json" || file.name.toLowerCase().endsWith(".json");
}

// a page that takes an invoice dropped anywhere on it
export default function DropPage({ className, busy, onJson, onImages, onRefused, children }: Props) {
  const [dragging, setDragging] = useState(false);

  function hasFiles(event: DragEvent) {
    return !busy && event.dataTransfer.types.includes("Files");
  }

  function take(files: File[]) {
    const json = files.find(isJson);
    const images = files.filter((file) => file.type.startsWith("image/"));
    if (json) {
      onJson([json]);
    } else if (images.length > 0) {
      onImages(images);
    } else {
      onRefused("Нужен JSON-файл или фото накладной");
    }
  }

  return (
    <main
      className={className}
      onDragOver={(event) => {
        if (hasFiles(event)) {
          event.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(event) => {
        // the event also fires when the pointer moves onto a child
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setDragging(false);
        }
      }}
      onDrop={(event) => {
        if (hasFiles(event)) {
          event.preventDefault();
          take(Array.from(event.dataTransfer.files));
        }
        setDragging(false);
      }}
    >
      {children}
      {dragging && (
        <div className="drop-overlay" aria-hidden="true">
          Отпустите файл, чтобы загрузить накладную
        </div>
      )}
    </main>
  );
}
