import { useEffect, useRef, useState } from "react";

export type Route =
  | { page: "invoices" }
  | { page: "upload" }
  | { page: "draft"; id: number }
  | { page: "posted"; id: number }
  | { page: "catalog" }
  | { page: "orders" }
  | { page: "ledger" }
  | { page: "report" }
  | { page: "traffic" };

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
    case "orders":
      return "#/orders";
    case "ledger":
      return "#/ledger";
    case "report":
      return "#/report";
    case "traffic":
      return "#/traffic";
    case "invoices":
      return "#/";
  }
}

export function sameRoute(a: Route, b: Route): boolean {
  return routeHash(a) === routeHash(b);
}

// the route follows the address, back and forward included
export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
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
