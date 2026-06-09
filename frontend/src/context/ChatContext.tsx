import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { postChat } from '../api';

interface Citation {
  filename: string;
  page: number;
  period: string | null;
  fund_name: string | null;
  chunk_text: string;
  file_path: string;
}

export interface Message {
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  is_out_of_corpus?: boolean;
}

interface ChatContextValue {
  messages: Message[];
  loading: boolean;
  send: (text: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

const STORAGE_KEY = 'altius_chat_messages';

function loadMessages(): Message[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Message[]) : [];
  } catch {
    return [];
  }
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  }, [messages]);

  const send = useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || loading) return;
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
  }, [loading]);

  return (
    <ChatContext.Provider value={{ messages, loading, send }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within a ChatProvider');
  return ctx;
}
