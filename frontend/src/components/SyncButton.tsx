import { useState, useRef } from 'react';

interface LogLine { type: string; text: string; }

export default function SyncButton() {
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  const append = (type: string, text: string) => {
    setLog(prev => [...prev, { type, text }]);
    setTimeout(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, 10);
  };

  const handleSync = () => {
    setRunning(true);
    setLog([]);

    const es = new EventSource('/api/sync', { withCredentials: false });

    // POST via fetch first — EventSource only does GET, so we use fetch for the POST
    // and read SSE from the response body manually.
    es.close();

    fetch('/api/sync', { method: 'POST' }).then(async (resp) => {
      if (!resp.body) { setRunning(false); return; }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() ?? '';
        for (const part of parts) {
          let evType = 'info', data = '';
          for (const line of part.split('\n')) {
            if (line.startsWith('event:')) evType = line.slice(6).trim();
            if (line.startsWith('data:')) data = line.slice(5).trim();
          }
          if (data) append(evType, data);
          if (evType === 'done') { setRunning(false); break; }
          if (evType === 'error' && data.length > 5) { /* keep running for partial errors */ }
        }
      }
      setRunning(false);
    }).catch(err => {
      append('error', String(err));
      setRunning(false);
    });
  };

  return (
    <>
      <button className="sync-btn" disabled={running} onClick={handleSync}>
        {running ? '⏳ Syncing…' : '🔄 Sync Portal'}
      </button>
      {log.length > 0 && (
        <div className="sync-log" ref={logRef}
          style={{ position: 'absolute', top: 44, right: 24, width: 520, zIndex: 100 }}>
          {log.map((l, i) => (
            <div key={i} className={`ev-${l.type}`}>[{l.type}] {l.text}</div>
          ))}
        </div>
      )}
    </>
  );
}
