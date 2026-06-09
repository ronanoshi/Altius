import { useState, useRef, useEffect } from 'react';
import { postChat } from '../api';

interface Citation {
  filename: string;
  page: number;
  period: string | null;
  fund_name: string | null;
  chunk_text: string;
  file_path: string;
}

interface Message {
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  is_out_of_corpus?: boolean;
}

const STORAGE_KEY = 'altius_chat_messages';

function loadMessages(): Message[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Message[]) : [];
  } catch {
    return [];
  }
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: q }]);
    setLoading(true);
    try {
      const data = await postChat(q);
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.answer,
        citations: data.citations,
        is_out_of_corpus: data.is_out_of_corpus,
      }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', text: `Error: ${e}` }]);
    } finally {
      setLoading(false);
    }
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
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Ask about the fund documents…"
          disabled={loading}
        />
        <button onClick={send} disabled={loading || !input.trim()}>Send</button>
      </div>
    </div>
  );
}
