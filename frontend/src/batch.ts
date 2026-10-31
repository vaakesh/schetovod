import { useRef, useState } from "react";

import { recognizeInvoice } from "./api";
import { message } from "./message";
import type { InvoiceDraft } from "./types";

export const MAX_SLOTS = 10;
const MAX_PHOTOS = 10;
const MAX_PHOTO_BYTES = 20 * 1024 * 1024;
// nginx refuses a request over 100 MB, the multipart wrapping takes some of it
const MAX_SLOT_BYTES = 95 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
// each recognition holds a database connection and takes minutes of the OpenAI limits
const MAX_RUNNING = 3;

const OFFLINE = "Сервер недоступен";

export type SlotStatus = "filling" | "queued" | "sending" | "done" | "failed";

export interface Slot {
  id: number;
  files: File[];
  status: SlotStatus;
  draft: InvoiceDraft | null;
  error: string | null;
  // why the last picked photos were not added
  refused: string | null;
}

export interface BatchUpload {
  slots: Slot[];
  // ready to be sent
  filled: number;
  // sent or waiting to be sent
  total: number;
  done: number;
  failed: number;
  running: boolean;
  // a null slot means a new one, the answer is the refusal when there is no room for it
  addFiles: (id: number | null, files: File[]) => string | null;
  removeFile: (id: number, file: File) => void;
  removeSlot: (id: number) => void;
  start: () => void;
  retry: (id: number) => void;
  clearDone: () => void;
}

function accept(present: File[], picked: File[]): { files: File[]; refused: string | null } {
  const files = [...present];
  const refused: string[] = [];
  for (const file of picked) {
    if (!PHOTO_TYPES.includes(file.type)) {
      refused.push(`${file.name}: нужен формат JPEG, PNG, WebP или GIF`);
    } else if (file.size > MAX_PHOTO_BYTES) {
      refused.push(`${file.name}: файл больше 20 МБ`);
    } else if (files.length >= MAX_PHOTOS) {
      refused.push(`${file.name}: в накладной уже ${MAX_PHOTOS} фото`);
    } else if (files.reduce((sum, item) => sum + item.size, file.size) > MAX_SLOT_BYTES) {
      refused.push(`${file.name}: вместе фото больше 95 МБ`);
    } else {
      files.push(file);
    }
  }
  return { files, refused: refused.length > 0 ? refused.join("\n") : null };
}

function failure(error: unknown): string {
  const text = message(error);
  // the answer is lost, not the invoice: a blind retry would make a second draft
  return text === OFFLINE
    ? `${text}. Черновик мог успеть создаться, перед повтором проверьте список накладных`
    : text;
}

export function useBatchUpload(): BatchUpload {
  const [slots, setSlots] = useState<Slot[]>([]);
  // the queue reads the list between renders, the state may lag behind it
  const current = useRef<Slot[]>([]);
  const nextId = useRef(1);

  function commit(next: Slot[]) {
    current.current = next;
    setSlots(next);
  }

  function patch(id: number, change: Partial<Slot>) {
    commit(current.current.map((slot) => (slot.id === id ? { ...slot, ...change } : slot)));
  }

  async function send(slot: Slot) {
    patch(slot.id, { status: "sending", error: null });
    try {
      const draft = await recognizeInvoice(slot.files);
      patch(slot.id, { status: "done", draft });
    } catch (error) {
      patch(slot.id, { status: "failed", error: failure(error) });
    }
    pump();
  }

  // runs from the handlers and not from an effect: StrictMode repeats effects,
  // and a repeated send is a second paid recognition
  function pump() {
    let running = current.current.filter((slot) => slot.status === "sending").length;
    for (const slot of current.current) {
      if (running >= MAX_RUNNING) {
        return;
      }
      if (slot.status === "queued") {
        running += 1;
        void send(slot);
      }
    }
  }

  function addFiles(id: number | null, picked: File[]): string | null {
    if (id !== null) {
      const slot = current.current.find((item) => item.id === id);
      if (slot) {
        patch(id, accept(slot.files, picked));
      }
      return null;
    }
    if (current.current.length >= MAX_SLOTS) {
      return `Не больше ${MAX_SLOTS} накладных за раз`;
    }
    commit([
      ...current.current,
      {
        id: nextId.current++,
        status: "filling",
        draft: null,
        error: null,
        ...accept([], picked),
      },
    ]);
    return null;
  }

  function removeFile(id: number, file: File) {
    const slot = current.current.find((item) => item.id === id);
    if (slot) {
      patch(id, { files: slot.files.filter((item) => item !== file), refused: null });
    }
  }

  function removeSlot(id: number) {
    // a request on its way cannot be taken back
    commit(current.current.filter((slot) => slot.id !== id || slot.status === "sending"));
  }

  function start() {
    commit(
      current.current.map((slot) =>
        slot.status === "filling" && slot.files.length > 0
          ? { ...slot, status: "queued", refused: null }
          : slot,
      ),
    );
    pump();
  }

  function retry(id: number) {
    patch(id, { status: "queued", error: null, refused: null });
    pump();
  }

  function clearDone() {
    commit(current.current.filter((slot) => slot.status !== "done"));
  }

  const count = (status: SlotStatus) => slots.filter((slot) => slot.status === status).length;
  const waiting = count("queued") + count("sending");

  return {
    slots,
    filled: slots.filter((slot) => slot.status === "filling" && slot.files.length > 0).length,
    total: waiting + count("done") + count("failed"),
    done: count("done"),
    failed: count("failed"),
    running: waiting > 0,
    addFiles,
    removeFile,
    removeSlot,
    start,
    retry,
    clearDone,
  };
}
