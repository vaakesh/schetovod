import { formatMoney, formatSigned } from "../format";
import type { ConfirmedInvoice } from "../types";

interface Props {
  result: ConfirmedInvoice;
  onHome: () => void;
}

export default function ConfirmedCard({ result, onHome }: Props) {
  return (
    <section className="confirmed">
      <div className="confirmed-mark">
        <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
      </div>
      <h1 className="hero-title">Накладная проведена</h1>
      <dl className="confirmed-figures">
        <div>
          <dt>В рознице</dt>
          <dd>+{formatMoney(result.retail_total)} ₽</dd>
        </div>
        {result.revaluation !== null && (
          <div>
            <dt>Переоценка</dt>
            <dd>{formatSigned(result.revaluation)} ₽</dd>
          </div>
        )}
        <div>
          <dt>Остаток</dt>
          <dd>{formatMoney(result.balance)} ₽</dd>
        </div>
      </dl>
      <p className="confirmed-meta">
        №{result.id} · запись журнала №{result.ledger_entry_id}
      </p>
      <div className="confirmed-actions">
        <button type="button" className="button confirmed-home" onClick={onHome}>
          <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="m3 10 9-7 9 7v9a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          На главную
        </button>
        <p className="confirmed-home-hint">К загрузке следующей накладной</p>
      </div>
    </section>
  );
}
