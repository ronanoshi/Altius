import { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import SyncButton from './components/SyncButton';
import { ChatProvider } from './context/ChatContext';
import Holdings from './pages/Holdings';
import Chat from './pages/Chat';
import Files from './pages/Files';
import Login from './pages/Login';

function isAuthed() {
  return sessionStorage.getItem('altius_authed') === '1';
}

export default function App() {
  const [authed, setAuthed] = useState(isAuthed);

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />;
  }

  return (
    <BrowserRouter>
      <ChatProvider>
        <nav style={{ position: 'relative' }}>
          <span className="title">Altius</span>
          <NavLink to="/" end>Holdings</NavLink>
          <NavLink to="/chat">Chat</NavLink>
          <NavLink to="/files">Files</NavLink>
          <SyncButton />
        </nav>
        <Routes>
          <Route path="/" element={<Holdings />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/files" element={<Files />} />
        </Routes>
      </ChatProvider>
    </BrowserRouter>
  );
}
