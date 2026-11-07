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
// a keyboard leaves little room, the list may come close to the edge
const SCREEN_GAP = 8;
// below the field while a few tags fit there
const MIN_HEIGHT = 160;
const MAX_HEIGHT = 360;

// the part of the page on screen in document coordinates,
// a tablet keyboard covers part of the window but window.innerHeight stays the same
function visibleArea(): { top: number; left: number; width: number; height: number } {
  const viewport = window.visualViewport;
  if (viewport) {
    return {
      top: viewport.pageTop,
      left: viewport.pageLeft,
      width: viewport.width,
      height: viewport.height,
    };
  }
  return {
    top: window.scrollY,
    left: window.scrollX,
    width: window.innerWidth,
    height: window.innerHeight,
  };
}

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

  // in the coordinates of the document, in body and outside the table, the table would clip it
  useLayoutEffect(() => {
    function place() {
      const rect = anchor.getBoundingClientRect();
      const view = visibleArea();
      const top = rect.top + window.scrollY;
      const bottom = rect.bottom + window.scrollY;
      const below = view.top + view.height - bottom - ANCHOR_GAP - SCREEN_GAP;
      const above = top - view.top - ANCHOR_GAP - SCREEN_GAP;
      const width = Math.min(WIDTH, view.width - 2 * SCREEN_GAP);
      const left = Math.max(
        view.left + SCREEN_GAP,
        Math.min(rect.left + window.scrollX, view.left + view.width - width - SCREEN_GAP),
      );
      setPosition(
        below >= MIN_HEIGHT || below >= above
          ? { top: bottom + ANCHOR_GAP, left, width, maxHeight: Math.min(below, MAX_HEIGHT) }
          : {
              // the list ends right above the field whatever its height
              top: top - ANCHOR_GAP,
              left,
              width,
              maxHeight: Math.min(above, MAX_HEIGHT),
              transform: "translateY(-100%)",
            },
      );
    }
    place();
    const viewport = window.visualViewport;
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    // a tablet keyboard shrinks and pans only the visual viewport
    viewport?.addEventListener("resize", place);
    viewport?.addEventListener("scroll", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
      viewport?.removeEventListener("resize", place);
      viewport?.removeEventListener("scroll", place);
    };
  }, [anchor]);

  const { found, searching, error } = suggestions;
  if (position === null || (found === null && !error)) {
    return null;
  }

  return createPortal(
    <div
      className="menu product-picker price-tag-suggest"
      style={position}
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
