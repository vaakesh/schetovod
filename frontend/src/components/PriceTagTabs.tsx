import type { Route } from "../router";
import SlidingThumb from "./SlidingThumb";

const TABS = [
  { page: "price-tags", label: "Печать" },
  { page: "price-tag-base", label: "База ценников" },
] as const;

interface Props {
  current: (typeof TABS)[number]["page"];
  go: (route: Route) => void;
}

// the form to print and the base of tags are two sides of one section
export default function PriceTagTabs({ current, go }: Props) {
  return (
    <div className="list-head">
      <div className="segments" role="tablist">
        <SlidingThumb selector=".segment.active" className="segment-thumb" />
        {TABS.map((tab) => (
          <button
            key={tab.page}
            type="button"
            role="tab"
            aria-selected={tab.page === current}
            className={tab.page === current ? "segment active" : "segment"}
            onClick={() => go({ page: tab.page })}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}
