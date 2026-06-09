import { useEffect, useState } from 'react';
import { getFiles, openFileUrl } from '../api';

interface FileRecord {
  id: number;
  filename: string;
  deal_name: string;
  file_type: string;
  classifier_confidence: number | null;
  download_date: string | null;
}

const BADGE: Record<string, string> = {
  capital_statement: 'badge-statement',
  report: 'badge-report',
  other: 'badge-other',
  unknown: 'badge-unknown',
};

const PAGE_SIZE = 40;

export default function Files() {
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);

  useEffect(() => {
    getFiles()
      .then(data => { setFiles(data); setPage(0); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const totalPages = Math.max(1, Math.ceil(files.length / PAGE_SIZE));
  const pageFiles = files.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="page">
      <h1>Files</h1>
      {loading && <p className="loading">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && !error && (
        <>
          <table>
            <thead>
              <tr>
                <th>Filename</th>
                <th>Type</th>
                <th>Confidence</th>
                <th>Deal</th>
                <th>Downloaded</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pageFiles.map(f => (
                <tr key={f.id}>
                  <td>{f.filename}</td>
                  <td>
                    <span className={`badge ${BADGE[f.file_type] ?? 'badge-unknown'}`}>
                      {f.file_type}
                    </span>
                  </td>
                  <td>{f.classifier_confidence != null ? `${(f.classifier_confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td>{f.deal_name}</td>
                  <td>{f.download_date ? f.download_date.slice(0, 10) : '—'}</td>
                  <td><a href={openFileUrl(f.id)} target="_blank" rel="noreferrer">Open</a></td>
                </tr>
              ))}
              {files.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: '#868e96' }}>No files yet — run Sync first.</td></tr>
              )}
            </tbody>
          </table>
          {files.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '1rem', fontSize: '0.875rem', color: '#868e96' }}>
              <span>
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, files.length)} of {files.length} results
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
