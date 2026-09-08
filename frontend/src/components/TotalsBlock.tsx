import { formatMoney } from "../format";
import type { InvoiceDraft } from "../types";

interface Props {
  draft: InvoiceDraft;
}

// the totals row of the lines table, each sum sits under the column it adds up
export default function TotalsBlock({ draft }: Props) {
  return (
    <tfoot>
      <tr>
        <td />
        <td className="total-label" colSpan={6}>
          Итого
        </td>
        <td className="num computed">{formatMoney(draft.totals.base_total)}</td>
        <td className="num">{formatMoney(draft.totals.cost_total)}</td>
        <td className="retail" />
        <td className="retail" />
        <td className="num computed total-accent retail">{formatMoney(draft.totals.retail_total)}</td>
        <td />
      </tr>
    </tfoot>
  );
}
