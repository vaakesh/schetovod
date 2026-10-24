import { formatMoney } from "../format";
import type { InvoiceDraft } from "../types";

interface Props {
  draft: InvoiceDraft;
  // false in the price view, where the purchase sums are hidden
  full: boolean;
}

// the totals row of the lines table, each sum sits under the column it adds up
export default function TotalsBlock({ draft, full }: Props) {
  return (
    <tfoot>
      <tr>
        <td />
        <td className="total-label" colSpan={full ? 7 : 5}>
          Итого
        </td>
        {full && (
          <>
            <td className="num computed">{formatMoney(draft.totals.base_total)}</td>
            <td className="num">{formatMoney(draft.totals.cost_total)}</td>
          </>
        )}
        <td className="retail" />
        <td className="num computed total-accent retail">{formatMoney(draft.totals.retail_total)}</td>
        <td />
      </tr>
    </tfoot>
  );
}
