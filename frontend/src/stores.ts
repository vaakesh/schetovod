export type Store = "gastronom" | "meat";

export const STORE_NAMES: Record<Store, string> = {
  gastronom: "Гастроном",
  meat: "Мясной магазин",
};

export function storePath(store: Store): string {
  return `/${store}/`;
}

export function resolveStore(pathname: string): Store | null {
  switch (pathname) {
    case "/":
    case "/gastronom":
    case "/gastronom/":
      return "gastronom";
    case "/meat":
    case "/meat/":
      return "meat";
    default:
      return null;
  }
}

export function apiPath(store: Store, path: string): string {
  return path.startsWith("/auth/") ? `/api${path}` : `/api/stores/${store}${path}`;
}
