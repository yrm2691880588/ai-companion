import { lazy, Suspense, useEffect } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Heart, PenLine, UserRound } from "lucide-react";
import Loading from "./components/Loading";
import { track } from "./lib/analytics";
const ChatPage = lazy(() => import("./pages/ChatPage"));
const CompanionsPage = lazy(() => import("./pages/CompanionsPage"));
const CreatePage = lazy(() => import("./pages/CreatePage"));
const MePage = lazy(() => import("./pages/MePage"));
const MemoryPage = lazy(() => import("./pages/MemoryPage"));
const PersonaPage = lazy(() => import("./pages/PersonaPage"));
const RoleplayPage = lazy(() => import("./pages/RoleplayPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

/** 一级导航：只放用户每天都会去的三处。设置属于系统配置，收进「我的」。 */
const NAV_ITEMS = [
  { to: "/", label: "伴侣", icon: Heart, end: true },
  { to: "/create", label: "创建", icon: PenLine, end: false },
  { to: "/me", label: "我的", icon: UserRound, end: false },
];

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
        <nav className="nav" aria-label="主导航">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className="nav-link">
              <Icon size={16} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="main">
        {/* 路由级懒加载：给骨架而不是一句「加载中…」，避免切换页面时白屏闪一下 */}
        <Suspense fallback={<Loading lines={3} label="页面加载中" />}>
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
