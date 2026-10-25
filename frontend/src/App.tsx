import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import type { Account } from "./types";
import ChatPage from "./pages/ChatPage";
import CompanionsPage from "./pages/CompanionsPage";
import CreatePage from "./pages/CreatePage";
import LoginPage from "./pages/LoginPage";
import MePage from "./pages/MePage";
import MemoryPage from "./pages/MemoryPage";
import RoleplayPage from "./pages/RoleplayPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => {
    api
      .me()
      .then(setAccount)
      .catch(() => {
        if (location.pathname !== "/login") navigate("/login", { replace: true });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          <NavLink to="/me">我的</NavLink>
          {account?.phone_masked ? (
            <span className="nav-user">{account.phone_masked}</span>
          ) : (
            <NavLink to="/login">登录</NavLink>
          )}
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<CompanionsPage />} />
          <Route path="/create" element={<CreatePage />} />
          <Route path="/companions/:id/chat" element={<ChatPage />} />
          <Route path="/companions/:id/memories" element={<MemoryPage />} />
          <Route path="/companions/:id/roleplay" element={<RoleplayPage />} />
          <Route path="/me" element={<MePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<p className="muted">页面不存在</p>} />
        </Routes>
      </main>
    </div>
  );
}
