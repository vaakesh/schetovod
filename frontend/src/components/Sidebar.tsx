import { routeHash, type Route } from "../router";
import { useTheme } from "../theme";
import type { Order } from "../types";
import Icon, { type IconName } from "./icons";
import SlidingThumb from "./SlidingThumb";

interface Item {
  route: Route;
  label: string;
  icon: IconName;
}

interface Group {
  title: string;
  items: Item[];
}

const GROUPS: Group[] = [
  {
    title: "Закупки",
    items: [
      { route: { page: "invoices" }, label: "Накладные", icon: "invoices" },
      { route: { page: "upload" }, label: "Загрузка", icon: "upload" },
      { route: { page: "orders" }, label: "Заказы", icon: "orders" },
    ],
  },
  {
    title: "Товары",
    items: [
      { route: { page: "catalog" }, label: "Каталог", icon: "catalog" },
      { route: { page: "price-tags" }, label: "Ценники", icon: "priceTag" },
    ],
  },
  {
    title: "Учёт",
    items: [
      { route: { page: "ledger" }, label: "Журнал", icon: "ledger" },
      { route: { page: "report" }, label: "Отчёт", icon: "report" },
    ],
  },
  {
    title: "Аналитика",
    items: [
      { route: { page: "traffic" }, label: "Покупатели", icon: "traffic" },
      { route: { page: "profit" }, label: "Прибыль", icon: "profit" },
    ],
  },
];

// a draft and a posted invoice belong to the invoices section, the base of tags to the tags
function section(route: Route): Route["page"] {
  if (route.page === "draft" || route.page === "posted") {
    return "invoices";
  }
  return route.page === "price-tag-base" ? "price-tags" : route.page;
}

interface Props {
  route: Route;
  cart: Order | null | undefined;
  uploading: boolean;
  // photos are being recognized, signing out would lose their answers
  working: boolean;
  go: (route: Route) => void;
  signOut: () => void;
}

export default function Sidebar({ route, cart, uploading, working, go, signOut }: Props) {
  const [theme, toggleTheme] = useTheme();
  const current = section(route);
  const themeLabel = theme === "dark" ? "Светлая тема" : "Тёмная тема";

  return (
    <aside className="sidebar">
      <button
        type="button"
        className="brand"
        aria-label="Счетовод — на главную"
        title="На главную"
        disabled={uploading}
        onClick={() => go({ page: "invoices" })}
      >
        <span className="brand-mark" aria-hidden="true">
          <Icon name="brand" size={16} />
        </span>
        <span className="brand-name">Счетовод</span>
      </button>

      <nav className="nav" aria-label="Разделы">
        <SlidingThumb selector=".nav-item.active" className="nav-thumb" />
        {GROUPS.map((group) => (
          <section key={group.title} className="nav-group" aria-label={group.title}>
            <h2 className="nav-title">{group.title}</h2>
            {group.items.map((item) => {
              const active = item.route.page === current;
              const count = item.route.page === "orders" && cart ? cart.lines.length : null;
              return (
                <a
                  key={item.route.page}
                  href={routeHash(item.route)}
                  className={active ? "nav-item active" : "nav-item"}
                  aria-current={active ? "page" : undefined}
                  onClick={(event) => {
                    event.preventDefault();
                    go(item.route);
                  }}
                >
                  <Icon name={item.icon} />
                  <span className="nav-label">{item.label}</span>
                  {count !== null && (
                    <span className="nav-badge" aria-label={`в заказе ${count}`}>
                      {count}
                    </span>
                  )}
                </a>
              );
            })}
          </section>
        ))}
      </nav>

      <div className="nav-bottom">
        <button
          type="button"
          className="nav-item nav-theme"
          title={themeLabel}
          onClick={toggleTheme}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} />
          <span className="nav-label">{themeLabel}</span>
        </button>
        <button
          type="button"
          className="nav-item nav-signout"
          title="Выйти"
          disabled={working}
          onClick={signOut}
        >
          <Icon name="signout" />
          <span className="nav-label">Выйти</span>
        </button>
      </div>
    </aside>
  );
}
