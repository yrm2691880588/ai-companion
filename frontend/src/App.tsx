import { Link, NavLink, Route, Routes } from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import CompanionsPage from "./pages/CompanionsPage";
import CreatePage from "./pages/CreatePage";
import LoginPage from "./pages/LoginPage";
import MemoryPage from "./pages/MemoryPage";
import RoleplayPage from "./pages/RoleplayPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          AI 伴侣
        </Link>
        <nav className="nav">
          <NavLink to="/" end>
            伴侣
          </NavLink>
          <NavLink to="/settings">模型与服务</NavLink>
          <NavLink to="/login">登录</NavLink>
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<CompanionsPage />} />
          <Route path="/create" element={<CreatePage />} />
          <Route path="/companions/:id/chat" element={<ChatPage />} />
          <Route path="/companions/:id/memories" element={<MemoryPage />} />
          <Route path="/companions/:id/roleplay" element={<RoleplayPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<p className="muted">页面不存在</p>} />
        </Routes>
      </main>
    </div>
  );
}
