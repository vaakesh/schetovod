import { useCallback, useState, type ReactNode } from "react";

import Modal from "./Modal";

export interface ConfirmOptions {
  title: string;
  text?: string;
  action: string;
  // a destructive action is red and the focus starts on cancel
  danger?: boolean;
}

interface Request {
  options: ConfirmOptions;
  resolve: (ok: boolean) => void;
}

interface Props {
  options: ConfirmOptions;
  onClose: (ok: boolean) => void;
}

function ConfirmDialog({ options, onClose }: Props) {
  return (
    <Modal onClose={() => onClose(false)}>
      <div className="modal-body">
        <h2 className="modal-title">{options.title}</h2>
        {options.text && <p className="modal-text">{options.text}</p>}
      </div>
      <div className="modal-actions">
        <button
          type="button"
          className="button button-ghost"
          autoFocus={options.danger}
          onClick={() => onClose(false)}
        >
          Отмена
        </button>
        <button
          type="button"
          className={options.danger ? "button button-danger" : "button button-primary"}
          autoFocus={!options.danger}
          onClick={() => onClose(true)}
        >
          {options.action}
        </button>
      </div>
    </Modal>
  );
}

export type Ask = (options: ConfirmOptions) => Promise<boolean>;

// window.confirm with a styled dialog, the element has to be rendered by the caller
export function useConfirm(): [Ask, ReactNode] {
  const [request, setRequest] = useState<Request | null>(null);

  // stable, so pages can keep it in effect dependencies
  const ask = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setRequest({ options, resolve })),
    [],
  );

  const element = request && (
    <ConfirmDialog
      options={request.options}
      onClose={(ok) => {
        request.resolve(ok);
        setRequest(null);
      }}
    />
  );
  return [ask, element];
}
