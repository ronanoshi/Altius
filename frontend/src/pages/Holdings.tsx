import { useEffect, useState } from 'react';
import { getHoldings } from '../api';

interface Holding {
  fund_name: string;
  current_value: number | null;
  statement_date: string | null;
  file_id: number;
}

export default function Holdings() {
  const [rows, setRows] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getHoldings()
      .then(setRows)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const fmt = (v: number | null) =>
    v == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

  const total = rows.reduce((s, r) => s + (r.current_value ?? 0), 0);

  return (
    <div className="page">
      <h1>Holdings</h1>
      {loading && <p className="loading">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && !error && (
        <>
          <table>
            <thead>
              <tr>
                <th>Fund</th>
                <th>Current Value</th>
                <th>As of</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.fund_name}>
                  <td>{r.fund_name}</td>
                  <td>{fmt(r.current_value)}</td>
                  <td>{r.statement_date ?? '—'}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={3} style={{ textAlign: 'center', color: '#868e96' }}>No statements extracted yet — run Sync first.</td></tr>
              )}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr>
                  <td><strong>Total</strong></td>
                  <td><strong>{fmt(total)}</strong></td>
                  <td></td>
                </tr>
              </tfoot>
            )}
          </table>
        </>
      )}
    </div>
  );
}
