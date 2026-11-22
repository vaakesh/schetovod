import { useEffect, useRef, useState, type MouseEvent } from "react";

import type { Store } from "./stores";

export type Route =
  | { page: "invoices" }
  | { page: "upload" }
  | { page: "draft"; id: number }
  | { page: "posted"; id: number }
  | { page: "catalog" }
  | { page: "price-tags" }
  | { page: "price-tag-base" }
  | { page: "orders" }
  | { page: "ledger" }
  | { page: "report" }
  | { page: "traffic" }
  | { page: "profit" }
  | { page: "purchases" };

export function parseRoute(hash: string): Route {
  const draft = hash.match(/^#\/invoice\/(\d+)$/);
  if (draft) {
    return { page: "draft", id: Number(draft[1]) };
  }
  const posted = hash.match(/^#\/posted\/(\d+)$/);
  if (posted) {
    return { page: "posted", id: Number(posted[1]) };
  }
  if (hash === "#/upload") {
    return { page: "upload" };
  }
  if (hash === "#/catalog") {
    return { page: "catalog" };
  }
  if (hash === "#/price-tags") {
    return { page: "price-tags" };
  }
  if (hash === "#/price-tags/base") {
    return { page: "price-tag-base" };
  }
  if (hash === "#/orders") {
    return { page: "orders" };
  }
  if (hash === "#/ledger") {
    return { page: "ledger" };
  }
  if (hash === "#/report") {
    return { page: "report" };
  }
  if (hash === "#/traffic") {
    return { page: "traffic" };
  }
  if (hash === "#/profit") {
    return { page: "profit" };
  }
  if (hash === "#/purchases") {
    return { page: "purchases" };
  }
  return { page: "invoices" };
}

export function routeHash(route: Route): string {
  switch (route.page) {
    case "draft":
      return `#/invoice/${route.id}`;
    case "posted":
      return `#/posted/${route.id}`;
    case "upload":
      return "#/upload";
    case "catalog":
      return "#/catalog";
    case "price-tags":
      return "#/price-tags";
    case "price-tag-base":
      return "#/price-tags/base";
    case "orders":
      return "#/orders";
    case "ledger":
      return "#/ledger";
    case "report":
      return "#/report";
    case "traffic":
      return "#/traffic";
    case "profit":
      return "#/profit";
    case "purchases":
      return "#/purchases";
    case "invoices":
      return "#/";
  }
}

export function sameRoute(a: Route, b: Route): boolean {
  return routeHash(a) === routeHash(b);
}

export function routeAvailable(store: Store, page: Route["page"]): boolean {
  return store === "gastronom" || !["orders", "traffic", "profit", "purchases"].includes(page);
}

const invoicesFallback: Route = { page: "invoices" };

export function storeSwitchRoute(store: Store, route: Route): Route {
  if (route.page === "draft" || route.page === "posted" || !routeAvailable(store, route.page)) {
    return invoicesFallback;
  }
  return route;
}

export function isPlainLinkClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  return (
    !event.defaultPrevented &&
    event.button === 0 &&
    !event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey
  );
}

// the route follows the address, back and forward included
export function useRoute(store: Store): Route {
  const [route, setRoute] = useState(() => availableRoute(store));

  useEffect(() => {
    const onChange = () => {
      const next = availableRoute(store);
      if (next === invoicesFallback) {
        replaceRoute(invoicesFallback);
      }
      setRoute((previous) => (sameRoute(previous, next) ? previous : next));
    };
    onChange();
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, [store]);

  return route;
}

function availableRoute(store: Store): Route {
  const route = parseRoute(window.location.hash);
  return routeAvailable(store, route.page) ? route : invoicesFallback;
}

export type RouteMotion = "forward" | "back" | "section";

// an invoice opens over its list
function depth(route: Route): number {
  return route.page === "draft" || route.page === "posted" ? 1 : 0;
}

// how the page enters: deeper from the right, back to the list from the left
export function useRouteMotion(route: Route): RouteMotion {
  const previous = useRef(route);
  const motion = useRef<RouteMotion>("section");
  if (previous.current !== route) {
    const change = depth(route) - depth(previous.current);
    motion.current = change > 0 ? "forward" : change < 0 ? "back" : "section";
    previous.current = route;
  }
  return motion.current;
}

// change the address without a new history entry and without a hashchange
export function replaceRoute(route: Route) {
  window.history.replaceState(null, "", routeHash(route));
}
