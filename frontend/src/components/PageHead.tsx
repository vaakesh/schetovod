import type { ReactNode } from "react";

import Icon from "./icons";

interface Props {
  title: ReactNode;
  meta?: ReactNode;
  // the parent list of a page opened from it
  back?: { label: string; onClick: () => void };
  children?: ReactNode;
}

export function BackLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className="back-link" onClick={onClick}>
      <Icon name="back" size={16} />
      {label}
    </button>
  );
}

export default function PageHead({ title, meta, back, children }: Props) {
  return (
    <header className="page-head">
      <div className="page-head-main">
        {back && <BackLink label={back.label} onClick={back.onClick} />}
        <h1 className="page-title">{title}</h1>
        {meta && <p className="page-head-meta">{meta}</p>}
      </div>
      {children && <div className="page-head-actions">{children}</div>}
    </header>
  );
}
