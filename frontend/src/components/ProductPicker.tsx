import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { searchProducts } from "../api";
import { formatMoney, formatNumber } from "../format";
import type { ProductSummary } from "../types";
import Icon from "./icons";
import Modal from "./Modal";

interface Props {
  supplierId: number;
  onPick: (product: ProductSummary) => void;
  onClose: () => void;
}

const SEARCH_DELAY_MS = 250;
const SCREEN_GAP = 8;
const MAX_SIZE = 420;

// the keyboard can shrink and pan the visual viewport without resizing the window
function pickerBounds() {
  const viewport = window.visualViewport;
  const width = viewport?.width ?? window.innerWidth;
  const height = viewport?.height ?? window.innerHeight;
  return {
    left: (viewport?.offsetLeft ?? 0) + width / 2,
    top: (viewport?.offsetTop ?? 0) + height / 2,
    width: Math.min(MAX_SIZE, width - 2 * SCREEN_GAP),
    height: Math.min(MAX_SIZE, height - 2 * SCREEN_GAP),
  };
}

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

export default function ProductPicker({ supplierId, onPick, onClose }: Props) {
  const [search, setSearch] = useState("");
  const [found, setFound] = useState<ProductSummary[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [bounds, setBounds] = useState(pickerBounds);
  const results = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const viewport = window.visualViewport;
    const fit = () => setBounds(pickerBounds());
    viewport?.addEventListener("resize", fit);
    viewport?.addEventListener("scroll", fit);
    window.addEventListener("resize", fit);
    fit();
    return () => {
      viewport?.removeEventListener("resize", fit);
      viewport?.removeEventListener("scroll", fit);
      window.removeEventListener("resize", fit);
    };
  }, []);

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
    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && count > 0) {
      event.preventDefault();
      const next = (active + (event.key === "ArrowDown" ? 1 : -1) + count) % count;
      setActive(next);
      results.current?.children[next]?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && found?.[active]) {
      event.preventDefault();
      onPick(found[active]);
    }
  }

  return (
    <Modal
      label="Выбор товара из каталога"
      className="catalog-picker"
      style={bounds}
      closeOnBackdrop={false}
      onClose={onClose}
    >
      <div className="catalog-picker-tools">
        <div className="menu-search">
          <input
            className="input"
            aria-label="Поиск товара"
            placeholder="Товар из каталога продавца"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={onKey}
          />
          {searching && <span className="spinner menu-spinner" />}
        </div>
        <button
          type="button"
          className="button button-ghost"
          aria-label="Закрыть каталог"
          ref={(button) => {
            // on touch screens the keyboard opens only when the user taps the search field
            if (button) {
              button.autofocus = window.matchMedia("(any-pointer: coarse)").matches;
            }
          }}
          onClick={onClose}
        >
          <Icon name="close" size={18} />
        </button>
      </div>
      {error && <div className="menu-empty menu-error">{error}</div>}
      <div className="menu-results" ref={results}>
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
    </Modal>
  );
}
