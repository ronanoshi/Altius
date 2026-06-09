import { useState, type FormEvent } from 'react';
import { postLogin } from '../api';

interface Props {
  onLogin: () => void;
}

export default function Login({ onLogin }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await postLogin(username, password);
      sessionStorage.setItem('altius_authed', '1');
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: '#f8f9fa',
    }}>
      <div style={{
        background: '#fff',
        border: '1px solid #dee2e6',
        borderRadius: '8px',
        padding: '2.5rem 2rem',
        width: '100%',
        maxWidth: '360px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
      }}>
        <h1 style={{ margin: '0 0 0.25rem', fontSize: '1.5rem' }}>Altius</h1>
        <p style={{ margin: '0 0 2rem', color: '#868e96', fontSize: '0.875rem' }}>
          Investor Document Platform
        </p>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.375rem', fontSize: '0.875rem', fontWeight: 500 }}>
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
          </div>
          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', marginBottom: '0.375rem', fontSize: '0.875rem', fontWeight: 500 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
          </div>
          {error && (
            <p style={{ margin: '0 0 1rem', color: '#e03131', fontSize: '0.875rem' }}>{error}</p>
          )}
          <button
            type="submit"
            disabled={loading || !username.trim() || !password.trim()}
            style={{ width: '100%' }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
