import { useLayoutEffect, useRef, type CSSProperties, type ReactNode } from "react";

interface Props {
  // escape, a click on the backdrop or a cancel button
  onClose: () => void;
  closeOnBackdrop?: boolean;
  className?: string;
  label?: string;
  style?: CSSProperties;
  children: ReactNode;
}

export default function Modal({
  onClose,
  closeOnBackdrop = true,
  className,
  label,
  style,
  children,
}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);

  // a modal dialog traps the focus and closes on escape by itself
  useLayoutEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  return (
    <dialog
      ref={dialog}
      aria-label={label}
      className={className ? `modal ${className}` : "modal"}
      style={style}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // a click on the backdrop lands on the dialog itself
        if (closeOnBackdrop && event.target === dialog.current) {
          onClose();
        }
      }}
    >
      {children}
    </dialog>
  );
}
