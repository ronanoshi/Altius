import { useState, useRef, useEffect } from 'react';
import { useChat } from '../context/ChatContext';

export default function Chat() {
  const { messages, loading, send } = useChat();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    send(q);
  };

  return (
    <div className="page chat-wrap">
      <h1>Chat</h1>
      <div className="messages">
        {messages.length === 0 && (
          <p style={{ color: '#868e96' }}>Ask a question about the fund documents.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="answer">{m.text}</div>
            {m.citations && m.citations.length > 0 && (
              <details className="citations">
                <summary>{m.citations.length} source(s)</summary>
                <ol>
                  {m.citations.map((c, j) => (
                    <li key={j}>
                      <strong>{c.filename}</strong> p{c.page}
                      {c.period && ` · ${c.period}`}
                      {c.fund_name && ` · ${c.fund_name}`}
                      <br />
                      <em>{c.chunk_text.slice(0, 120)}…</em>
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        ))}
        {loading && <div className="msg assistant loading">Thinking…</div>}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder="Ask about the fund documents…"
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading || !input.trim()}>Send</button>
      </div>
    </div>
  );
}
