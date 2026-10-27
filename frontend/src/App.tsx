import { lazy, Suspense, useEffect } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { track } from "./lib/analytics";
const ChatPage = lazy(() => import("./pages/ChatPage"));
const CompanionsPage = lazy(() => import("./pages/CompanionsPage"));
const CreatePage = lazy(() => import("./pages/CreatePage"));
const MePage = lazy(() => import("./pages/MePage"));
const MemoryPage = lazy(() => import("./pages/MemoryPage"));
const PersonaPage = lazy(() => import("./pages/PersonaPage"));
const RoleplayPage = lazy(() => import("./pages/RoleplayPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

export default function App() {
  // 每次应用启动上报一次，用于判断真实打开次数
  useEffect(() => {
    track("app_open");
  }, []);

  return (
    <div className="app">
      <Toaster position="top-center" visibleToasts={3} duration={3000} />
      <header className="topbar">
        <Link to="/" className="brand">
          AI 伴侣
        </Link>
        <nav className="nav">
          <NavLink to="/" end>
            伴侣
          </NavLink>
          <NavLink to="/create">创建</NavLink>
          <NavLink to="/me">我的</NavLink>
        </nav>
      </header>
      <main className="main">
        <Suspense fallback={<p className="muted">加载中…</p>}>
        <Routes>
          <Route path="/" element={<CompanionsPage />} />
          <Route path="/create" element={<CreatePage />} />
          <Route path="/companions/:id/chat" element={<ChatPage />} />
          <Route path="/companions/:id/persona" element={<PersonaPage />} />
          <Route path="/companions/:id/memories" element={<MemoryPage />} />
          <Route path="/companions/:id/roleplay" element={<RoleplayPage />} />
          <Route path="/me" element={<MePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<p className="muted">页面不存在</p>} />
        </Routes>
        </Suspense>
      </main>
    </div>
  );
}
