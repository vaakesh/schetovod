import { useEffect, useId, useState, type KeyboardEvent, type RefObject } from "react";

import { request } from "../api";
import { nameKey, stocktakeHint, type CountDocument, type Suggestion } from "../stocktakes";

interface Props {
  doc: CountDocument;
  value: string;
  editing: number | null;
  input: RefObject<HTMLInputElement | null>;
  onChange: (value: string) => void;
  onPick: (suggestion: Suggestion) => void;
}

export default function StocktakeName({
  doc,
  value,
  editing,
  input,
  onChange,
  onPick,
}: Props) {
  const listId = useId();
  const key = nameKey(value);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [results, setResults] = useState<{ key: string; items: Suggestion[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!open || !key) return;
    let live = true;
    setFailed(false);
    const timer = window.setTimeout(() => {
      request<Suggestion[]>("GET", `/stocktakes/${doc.id}/suggestions?q=${encodeURIComponent(key)}`)
        .then((items) => live && setResults({ key, items }))
        .catch(() => live && setFailed(true));
    }, 140);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [doc.id, doc.version, key, open, attempt]);

  const current =
    key && open
      ? doc.lines.filter((line) => line.id !== editing && nameKey(line.name).includes(key))
      : [];
  const items: Suggestion[] = current.map((line) => ({
    ...line,
    current_line_id: line.id,
    current_quantity: line.quantity,
    current_amount: line.amount,
  }));
  const seen = new Set(items.map((item) => nameKey(item.name)));
  if (results?.key === key) {
    items.push(
      ...results.items.filter(
        (item) => item.current_line_id === null && !seen.has(nameKey(item.name)),
      ),
    );
  }
  const options = items
    .sort((a, b) => Number(nameKey(b.name) === key) - Number(nameKey(a.name) === key))
    .slice(0, 15);
  const expanded = open && Boolean(key) && options.length > 0;

  function select(item: Suggestion) {
    setOpen(false);
    onPick(item);
  }
  function keys(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") setOpen(false);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      if (options.length) {
        const direction = event.key === "ArrowDown" ? 1 : -1;
        const next =
          active < 0
            ? direction > 0
              ? 0
              : options.length - 1
            : (active + direction + options.length) % options.length;
        setActive(next);
        document.getElementById(`${listId}-${next}`)?.scrollIntoView({ block: "nearest" });
      }
    } else if (event.key === "Enter" && expanded && options[active]) {
      event.preventDefault();
      select(options[active]!);
    }
  }

  return (
    <div
      className="field count-name"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <label className="field-label" htmlFor={listId + "-name"}>
        Название
      </label>
      <input
        ref={input}
        id={listId + "-name"}
        className="input"
        role="combobox"
        aria-haspopup="listbox"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={expanded ? listId : undefined}
        aria-activedescendant={expanded && options[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        required
        maxLength={300}
        value={value}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value);
          setActive(-1);
          setOpen(true);
        }}
        onKeyDown={keys}
      />
      {expanded && (
        <ul role="listbox" id={listId} aria-label="Найденные товары" className="count-options">
          {options.map((item, index) => (
            <li role="none" key={nameKey(item.name)}>
              <button
                type="button"
                role="option"
                aria-selected={active === index}
                id={`${listId}-${index}`}
                tabIndex={-1}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => select(item)}
              >
                <span>
                  <strong>{item.name}</strong>
                  <small>{stocktakeHint(item, item.current_quantity, item.current_amount)}</small>
                </span>
                {item.current_line_id !== null && <span className="count-option-action">Изменить</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && key && failed && (
        <button type="button" className="count-link" onClick={() => setAttempt((n) => n + 1)}>
          Повторить поиск
        </button>
      )}
    </div>
  );
}
