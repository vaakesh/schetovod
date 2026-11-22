import { useEffect, useState } from "react";

import { getPurchaseOverview } from "../api";
import { formatNumber } from "../format";
import { message } from "../message";
import type { PurchasePeriod } from "../types";
import { purchaseMoney } from "./PurchaseControls";

export default function PurchaseOverview({ period, supplierId, supplierName }: {
  period: PurchasePeriod; supplierId: number | null; supplierName?: string;
}) {
  const [totals, setTotals] = useState<Awaited<ReturnType<typeof getPurchaseOverview>> | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    setError("");
    getPurchaseOverview(period, supplierId)
      .then((result) => current && setTotals(result))
      .catch((reason) => current && setError(message(reason)));
    return () => { current = false; };
  }, [period, supplierId, attempt]);
  if (error) return <div role="alert" className="sheet purchase-overview">{error} <button className="button button-ghost"
    onClick={() => setAttempt(attempt + 1)}>Повторить</button></div>;
  return <dl className="sheet purchase-overview" aria-label="Итоги закупок за период" aria-busy={!totals}>
    <div><dt>Расходы за период</dt><dd>{totals ? purchaseMoney(totals.spend) : "…"}</dd></div>
    <div><dt>Накладных</dt><dd>{totals ? formatNumber(totals.invoices) : "…"}</dd></div>
    {supplierName && <div className="purchase-total-supplier"><dt>Поставщик</dt><dd>{supplierName}</dd></div>}
  </dl>;
}
