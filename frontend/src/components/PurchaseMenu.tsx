import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

import Icon, { type IconName } from "./icons";

interface Props<T extends string> {
  label: string;
  value: T;
  groups: readonly { label?: string; options: readonly (readonly [T, string])[] }[];
  icon?: IconName;
  title?: string;
  onChange: (value: T) => void;
}

export default function PurchaseMenu<T extends string>({ label, value, groups, icon, title, onChange }: Props<T>) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const menuRef = useRef<HTMLDivElement>(null);
  const search = useRef({ text: "", time: 0 });
  const selectedTitle = title ?? groups.flatMap((group) => group.options).find(([key]) => key === value)?.[1];

  useLayoutEffect(() => {
    if (!open) return;
    const selected = root.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]');
    selected?.focus({ preventScroll: true });
    const menu = menuRef.current;
    if (menu && selected) {
      menu.scrollTop = Math.max(0, selected.getBoundingClientRect().bottom - menu.getBoundingClientRect().bottom + 8);
    }
    search.current.text = "";
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function close() {
    setOpen(false);
    trigger.current?.focus({ preventScroll: true });
  }

  function move(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button"));
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    let next: number;
    switch (event.key) {
      case "ArrowDown": next = (index + 1) % buttons.length; break;
      case "ArrowUp": next = (index - 1 + buttons.length) % buttons.length; break;
      case "ArrowLeft":
      case "ArrowRight": {
        const option = buttons[index];
        if (option?.parentElement?.getAttribute("role") !== "group") return;
        const sibling = event.key === "ArrowLeft" ? option?.previousElementSibling : option?.nextElementSibling;
        if (!(sibling instanceof HTMLButtonElement)) return;
        next = buttons.indexOf(sibling);
        break;
      }
      case "Home": next = 0; break;
      case "End": next = buttons.length - 1; break;
      default: {
        if (!event.key.trim() || event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return;
        const now = Date.now();
        const prefix = now - search.current.time < 600 ? search.current.text : "";
        search.current = { text: prefix + event.key.toLocaleLowerCase("ru"), time: now };
        next = buttons.findIndex((button) => button.textContent.trim().toLocaleLowerCase("ru").startsWith(search.current.text));
        if (next < 0) return;
      }
    }
    event.preventDefault();
    buttons[next]?.focus();
  }

  return <div className="purchase-menu" ref={root}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button type="button" ref={trigger} className="input purchase-menu-trigger"
      aria-label={`${label}: ${selectedTitle}`} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen(!open)} onKeyDown={(event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          setOpen(true);
        }
      }}>
      {icon && <Icon name={icon} size={16} />}
      <span>{selectedTitle}</span><Icon name="chevronRight" size={13} />
    </button>
    {open && <div ref={menuRef} className="menu purchase-options" id={id} role="menu" aria-label={label} onKeyDown={move}>
      {groups.map((group) => <div key={group.label ?? label} className="purchase-menu-group"
        role={group.label ? "group" : "none"} aria-label={group.label}>
        {group.label && <div className="purchase-group-label" aria-hidden="true">{group.label}</div>}
        {group.options.map(([key, text]) => <button type="button" role="menuitemradio" aria-checked={key === value}
          key={key} tabIndex={-1} className={key === value ? "menu-item selected" : "menu-item"}
          onClick={() => { onChange(key); close(); }}>
          <span>{text}</span>{key === value && <Icon name="check" size={15} />}
        </button>)}
      </div>)}
    </div>}
  </div>;
}
