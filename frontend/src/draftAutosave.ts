import type { DraftForm, InvoiceDraft } from "./types";

export interface DraftSaveState {
  draft: InvoiceDraft;
  form: DraftForm;
  saving: boolean;
  error: string | null;
  saved: boolean;
}

interface Options {
  draft: InvoiceDraft;
  send: (form: DraftForm) => Promise<InvoiceDraft>;
  delay?: number;
}

// one writer per open draft, newer edits wait for the current request
export class DraftAutosave {
  private state: DraftSaveState;
  private send: Options["send"];
  private delay: number;
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private request: Promise<boolean> | null = null;
  private changedAt = 0;
  private stopped = false;

  constructor({ draft, send, delay = 700 }: Options) {
    this.state = { draft, form: draft.form, saving: false, error: null, saved: false };
    this.send = send;
    this.delay = delay;
  }

  getSnapshot = (): DraftSaveState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  get dirty(): boolean {
    return JSON.stringify(this.state.form) !== JSON.stringify(this.state.draft.form);
  }

  private publish(changes: Partial<DraftSaveState>) {
    this.state = { ...this.state, ...changes };
    this.listeners.forEach((listener) => listener());
  }

  private clearTimer() {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private schedule() {
    this.clearTimer();
    if (this.stopped || this.request || !this.dirty || this.state.error) {
      return;
    }
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.save();
    }, Math.max(0, this.changedAt + this.delay - Date.now()));
  }

  update = (change: (form: DraftForm) => DraftForm): void => {
    this.changedAt = Date.now();
    this.publish({ form: change(this.state.form), error: null });
    this.schedule();
  };

  reset = (): void => {
    if (this.request) {
      return;
    }
    this.clearTimer();
    this.publish({ form: this.state.draft.form, error: null });
  };

  private save(): Promise<boolean> {
    if (this.request) {
      return this.request;
    }
    if (!this.dirty || this.stopped) {
      return Promise.resolve(!this.dirty);
    }
    const sent = this.state.form;
    this.clearTimer();
    this.request = Promise.resolve()
      .then(() => this.send(sent))
      .then((draft) => {
        // normalization belongs only to the submitted version, never to newer input
        const unchanged = JSON.stringify(this.state.form) === JSON.stringify(sent);
        this.publish({ draft, form: unchanged ? draft.form : this.state.form, saved: true });
        return true;
      })
      .catch((reason: unknown) => {
        if (JSON.stringify(this.state.form) === JSON.stringify(sent)) {
          this.publish({ error: reason instanceof Error ? reason.message : String(reason) });
        }
        return false;
      })
      .finally(() => {
        this.request = null;
        this.publish({ saving: false });
        this.schedule();
      });
    this.publish({ saving: true, error: null });
    return this.request;
  }

  // navigation and an explicit retry wait until the latest edits reach the server
  flush = async (): Promise<boolean> => {
    this.clearTimer();
    while (this.request || this.dirty) {
      if (!(await this.save())) {
        return false;
      }
      this.clearTimer();
    }
    return true;
  };

  stop = (): void => {
    this.stopped = true;
    this.clearTimer();
    this.listeners.clear();
  };
}
