import { useEffect, useState } from "react";

import { getPosted } from "../api";
import { formatDate, formatMoney, formatNumber, formatText } from "../format";
import { message } from "../message";
import type { Route } from "../router";
import type { PostedInvoice } from "../types";

interface Props {
  id: number;
  go: (route: Route) => void;
}

export default function PostedInvoicePage({ id, go }: Props) {
  const [invoice, setInvoice] = useState<PostedInvoice | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPosted(id)
      .then(setInvoice)
      .catch((reason) => setError(message(reason)));
  }, [id]);

  if (error) {
    return (
      <main className="page page-empty">
        <h1 className="hero-title">Накладная не открылась</h1>
        <div className="alert">
          <pre>{error}</pre>
        </div>
        <button
          type="button"
          className="button button-ghost back-button"
          onClick={() => go({ page: "invoices" })}
        >
          К накладным
        </button>
      </main>
    );
  }

  if (!invoice) {
    return (
      <main className="page page-empty">
        <span className="spinner page-spinner" />
      </main>
    );
  }

  return (
    <main className="page">
      <section className="invoice-head">
        <h1 className="invoice-title">
          <span className="title-word">Накладная</span>
          <span>{invoice.invoice_number}</span>
          <span className="title-word">от</span>
          <span>{formatDate(invoice.invoice_date)}</span>
        </h1>
        <div className="supplier-static">
          <span className="supplier-name">{invoice.supplier.name}</span>
          <span className="supplier-meta">ИНН {formatText(invoice.supplier.inn)}</span>
        </div>
      </section>

      <section className="sheet">
        <div className="table-wrap">
          <table className="lines posted">
            <colgroup>
              <col className="col-no" />
              <col className="col-name" />
            </colgroup>
            <thead>
              <tr className="groups">
                <th colSpan={4} />
                <th colSpan={4} className="group group-start">
                  Закупка
                </th>
                <th colSpan={3} className="group group-start retail">
                  Розница
                </th>
              </tr>
              <tr>
                <th className="num">№</th>
                <th>Название</th>
                <th className="num">Кол-во</th>
                <th>Ед.</th>
                <th className="num group-start">Цена без НДС</th>
                <th className="num">НДС, %</th>
                <th className="num">Цена с НДС</th>
                <th className="num">Сумма с НДС</th>
                <th className="num group-start">Наценка, %</th>
                <th className="num">Цена</th>
                <th className="num">Сумма</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.map((line) => (
                <tr key={line.line_no} className="line">
                  <td className="num index">{line.line_no}</td>
                  <td>
                    <span className="posted-name">{line.name}</span>
                    {line.product_name !== line.name && (
                      <span className="tag">в каталоге: {line.product_name}</span>
                    )}
                  </td>
                  <td className="num">{formatNumber(line.quantity)}</td>
                  <td>{formatText(line.unit)}</td>
                  <td className="num computed group-start">{formatMoney(line.base_price)}</td>
                  <td className="num computed">{formatNumber(line.vat_percent)}</td>
                  <td className="num computed">{formatMoney(line.cost_price)}</td>
                  <td className="num">{formatMoney(line.cost_price_total)}</td>
                  <td className="num computed group-start">{formatNumber(line.markup_pct)}</td>
                  <td className="num">{formatMoney(line.retail_price)}</td>
                  <td className="num strong">{formatMoney(line.retail_price_total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td />
                <td className="total-label" colSpan={6}>
                  Итого
                </td>
                <td className="num">{formatMoney(invoice.cost_total)}</td>
                <td />
                <td />
                <td className="num total-accent">{formatMoney(invoice.retail_total)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

    </main>
  );
}
