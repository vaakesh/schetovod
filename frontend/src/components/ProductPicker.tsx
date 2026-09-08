import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { searchProducts } from "../api";
import { formatMoney, formatNumber } from "../format";
import type { ProductSummary } from "../types";

interface Props {
  supplierId: number;
  // the element the popover opens under
  anchor: HTMLElement;
  onPick: (product: ProductSummary) => void;
  onClose: () => void;
}

const SEARCH_DELAY_MS = 250;
const WIDTH = 420;
const ANCHOR_GAP = 6;
// room kept between the popover and the edge of the screen
const SCREEN_GAP = 24;
// enough for the search field and a few products
const MIN_HEIGHT = 260;
// a taller list would cover most of the table
const MAX_HEIGHT = 420;

function details(product: ProductSummary): string {
  if (product.cost_price === null) {
    return `ещё не закупался · наценка ${formatNumber(product.markup_pct)}%`;
  }
  return [
    `закупка ${formatMoney(product.cost_price)} ₽`,
    `розница ${formatMoney(product.retail_price)} ₽`,
    `наценка ${formatNumber(product.markup_pct)}%`,
  ].join(" · ");
}

export default function ProductPicker({ supplierId, anchor, onPick, onClose }: Props) {
  const [search, setSearch] = useState("");
  const [found, setFound] = useState<ProductSummary[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState<React.CSSProperties | null>(null);
  const root = useRef<HTMLDivElement>(null);

  // fixed next to the anchor, the table scrolls sideways and would clip an absolute popover
  useLayoutEffect(() => {
    const rect = anchor.getBoundingClientRect();
    // the action dock covers the bottom of the screen, the popover keeps clear of it
    const floor = Math.min(
      window.innerHeight,
      document.querySelector(".dock")?.getBoundingClientRect().top ?? window.innerHeight,
    );
    const below = floor - rect.bottom - ANCHOR_GAP - SCREEN_GAP;
    const above = rect.top - ANCHOR_GAP - SCREEN_GAP;
    const left = Math.max(SCREEN_GAP, Math.min(rect.left, window.innerWidth - WIDTH - SCREEN_GAP));
    // below the line unless it is cramped there and there is more room above
    setPosition(
      below >= MIN_HEIGHT || below >= above
        ? { top: rect.bottom + ANCHOR_GAP, left, maxHeight: Math.min(below, MAX_HEIGHT) }
        : {
            bottom: window.innerHeight - rect.top + ANCHOR_GAP,
            left,
            maxHeight: Math.min(above, MAX_HEIGHT),
          },
    );
  }, [anchor]);

  // closes on a click outside, on escape and when the page moves under it
  useEffect(() => {
    function onPointer(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) {
        onClose();
      }
    }
    function onScroll(event: Event) {
      if (!root.current?.contains(event.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onClose);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onClose);
    };
  }, [onClose]);

  useEffect(() => {
    // a newer query cancels the answer to an older one
    let current = true;
    setSearching(true);
    setError(null);
    const timer = window.setTimeout(() => {
      searchProducts(supplierId, search)
        .then((result) => {
          if (current) {
            setFound(result);
            setActive(0);
          }
        })
        .catch((reason) => current && setError(reason instanceof Error ? reason.message : String(reason)))
        .finally(() => current && setSearching(false));
    }, SEARCH_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [supplierId, search]);

  function onKey(event: React.KeyboardEvent) {
    const count = found?.length ?? 0;
    if (event.key === "Escape") {
      onClose();
    } else if (event.key === "ArrowDown" && count > 0) {
      event.preventDefault();
      setActive((index) => (index + 1) % count);
    } else if (event.key === "ArrowUp" && count > 0) {
      event.preventDefault();
      setActive((index) => (index - 1 + count) % count);
    } else if (event.key === "Enter" && found?.[active]) {
      event.preventDefault();
      onPick(found[active]);
    }
  }

  if (position === null) {
    return null;
  }

  return createPortal(
    <div
      ref={root}
      className="menu product-picker"
      style={{ ...position, width: WIDTH }}
    >
      <div className="menu-search">
        <input
          className="input"
          autoFocus
          placeholder="Товар из каталога продавца"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onKeyDown={onKey}
        />
        {searching && <span className="spinner menu-spinner" />}
      </div>
      {error && <div className="menu-empty menu-error">{error}</div>}
      <div className="menu-results">
        {found?.map((product, index) => (
          <button
            key={product.id}
            type="button"
            className={index === active ? "menu-item active" : "menu-item"}
            onMouseEnter={() => setActive(index)}
            onClick={() => onPick(product)}
          >
            <span className="menu-title">{product.name}</span>
            <span className="menu-meta">{details(product)}</span>
          </button>
        ))}
      </div>
      {found !== null && found.length === 0 && !searching && (
        <div className="menu-empty">
          {search.trim()
            ? "Ничего не нашли. Впишите название в строку — будет новый товар."
            : "У продавца пока нет товаров."}
        </div>
      )}
    </div>,
    document.body,
  );
}
