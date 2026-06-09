import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import SyncButton from './components/SyncButton';
import Holdings from './pages/Holdings';
import Chat from './pages/Chat';
import Files from './pages/Files';

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
