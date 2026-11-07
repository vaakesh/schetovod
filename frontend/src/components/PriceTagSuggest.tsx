import { useEffect, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

import { searchPriceTags } from "../api";
import { message } from "../message";
import { tagDetails } from "../priceTags";
import type { PriceTag } from "../types";

const SEARCH_DELAY_MS = 250;
export const MIN_QUERY = 2;
const WIDTH = 460;
const ANCHOR_GAP = 6;
const SCREEN_GAP = 24;
const MAX_HEIGHT = 360;

export interface Suggestions {
  found: PriceTag[] | null;
  searching: boolean;
  error: string | null;
}

// the tags matching what is typed in the name, null query stops the search
export function usePriceTagSearch(query: string | null): Suggestions {
  const [state, setState] = useState<Suggestions>({ found: null, searching: false, error: null });
  const text = query?.trim() ?? "";

  useEffect(() => {
    if (text.length < MIN_QUERY) {
      setState({ found: null, searching: false, error: null });
      return;
    }
    // a newer query cancels the answer to an older one
    let current = true;
    setState((previous) => ({ ...previous, searching: true, error: null }));
    const timer = window.setTimeout(() => {
      searchPriceTags(text)
        .then((found) => current && setState({ found, searching: false, error: null }))
        .catch(
          (reason) => current && setState({ found: null, searching: false, error: message(reason) }),
        );
    }, SEARCH_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [text]);

  return state;
}

interface Props {
  // the name field the list opens under
  anchor: HTMLElement;
  suggestions: Suggestions;
  active: number;
  onActive: (index: number) => void;
  onPick: (tag: PriceTag) => void;
}

// a list under the name field, the field keeps the focus and the keys
export default function PriceTagSuggest({ anchor, suggestions, active, onActive, onPick }: Props) {
  const [position, setPosition] = useState<React.CSSProperties | null>(null);

  // fixed next to the field, the table scrolls sideways and would clip an absolute list
  useLayoutEffect(() => {
    function place() {
      const rect = anchor.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - ANCHOR_GAP - SCREEN_GAP;
      const above = rect.top - ANCHOR_GAP - SCREEN_GAP;
      const left = Math.max(
        SCREEN_GAP,
        Math.min(rect.left, window.innerWidth - WIDTH - SCREEN_GAP),
      );
      setPosition(
        below >= 200 || below >= above
          ? { top: rect.bottom + ANCHOR_GAP, left, maxHeight: Math.min(below, MAX_HEIGHT) }
          : {
              bottom: window.innerHeight - rect.top + ANCHOR_GAP,
              left,
              maxHeight: Math.min(above, MAX_HEIGHT),
            },
      );
    }
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [anchor]);

  const { found, searching, error } = suggestions;
  if (position === null || (found === null && !error)) {
    return null;
  }

  return createPortal(
    <div
      className="menu product-picker price-tag-suggest"
      style={{ ...position, width: WIDTH }}
      // a click on the list must not take the focus from the field
      onMouseDown={(event) => event.preventDefault()}
    >
      {error && <div className="menu-empty menu-error">{error}</div>}
      <div className="menu-results">
        {found?.map((tag, index) => (
          <button
            key={tag.id}
            type="button"
            tabIndex={-1}
            className={index === active ? "menu-item active" : "menu-item"}
            onMouseEnter={() => onActive(index)}
            onClick={() => onPick(tag)}
          >
            <span className="menu-title">
              {tag.name}
              {tag.subtitle && <span className="price-tag-subtitle"> {tag.subtitle}</span>}
            </span>
            <span className="menu-meta">{tagDetails(tag)}</span>
          </button>
        ))}
      </div>
      {found !== null && found.length === 0 && !searching && (
        <div className="menu-empty">Такого ценника ещё нет, заполните строку — он сохранится</div>
      )}
    </div>,
    document.body,
  );
}
