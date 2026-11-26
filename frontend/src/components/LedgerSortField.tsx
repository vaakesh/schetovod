import type { LedgerSort } from "../types";

interface Props {
  sort: LedgerSort;
  onSort: (sort: LedgerSort) => void;
}

export default function LedgerSortField({ sort, onSort }: Props) {
  return (
    <label className="field">
      <span className="field-label">Сортировка</span>
      <select
        className="input"
        value={sort}
        onChange={(event) => onSort(event.target.value as LedgerSort)}
      >
        <option value="number">По номеру</option>
        <option value="kind">По виду операции</option>
      </select>
    </label>
  );
}
