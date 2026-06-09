import { useEffect, useState } from 'react';
import { getHoldings } from '../api';

interface Holding {
  fund_name: string;
  current_value: number | null;
  statement_date: string | null;
  file_id: number;
}

const PAGE_SIZE = 40;

export default function Holdings() {
  const [rows, setRows] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);

  useEffect(() => {
    getHoldings()
      .then(data => { setRows(data); setPage(0); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const fmt = (v: number | null) =>
    v == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

  // Total always sums the full dataset, not just the current page
  const total = rows.reduce((s, r) => s + (r.current_value ?? 0), 0);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

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
              {pageRows.map(r => (
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
                  <td><strong>Total (all {rows.length})</strong></td>
                  <td><strong>{fmt(total)}</strong></td>
                  <td></td>
                </tr>
              </tfoot>
            )}
          </table>
          {rows.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '1rem', fontSize: '0.875rem', color: '#868e96' }}>
              <span>
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, rows.length)} of {rows.length} results
              </span>
              {totalPages > 1 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <button onClick={() => setPage(p => p - 1)} disabled={page === 0}>← Prev</button>
                  <span>Page {page + 1} of {totalPages}</span>
                  <button onClick={() => setPage(p => p + 1)} disabled={page >= totalPages - 1}>Next →</button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
