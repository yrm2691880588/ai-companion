import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import AppearanceCard from "../components/AppearanceCard";
import type { Account } from "../types";

export default function MePage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .me()
      .then(setAccount)
      .catch(() => setAccount(null));
  }, []);

  async function logout() {
    try {
      await api.logout();
      window.location.href = "/login";
    } catch (event) {
      setError((event as Error).message);
    }
  }

  return (
    <div>
      <h1>我的</h1>
      <p className="muted">账号、外观、隐私与反馈都在这里；模型与用量只对管理员开放。</p>

      {error && <div className="alert">{error}</div>}

      <div className="card" style={{ marginTop: 12 }}>
        <h2>账号</h2>
        {account?.phone_masked ? (
          <p>
            {account.phone_masked}
            <button className="ghost" style={{ marginLeft: 10 }} onClick={() => void logout()}>
              退出登录
            </button>
          </p>
        ) : (
          <p className="muted">
            当前是开发模式（未登录）。
            <Link to="/login" style={{ marginLeft: 6 }}>
              去登录
            </Link>
          </p>
        )}
        {account?.role === "admin" && <p className="muted">管理员账号</p>}
      </div>

      <div style={{ marginTop: 12 }}>
        <AppearanceCard />
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h2>隐私与数据</h2>
        <p className="muted">你的对话与记忆只属于这个账号；删除伴侣会一并清理关联数据。</p>
        <div className="toolbar">
          <a className="btn ghost" href="/v1/me/export" target="_blank" rel="noreferrer">
            导出我的数据（JSON）
          </a>
          {account?.role === "admin" && (
            <Link className="btn ghost" to="/settings">
              模型与用量（管理员）
            </Link>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h2>关于</h2>
        <p className="muted">AI 伴侣系统 v0.1.0 · 内测中，欢迎把问题告诉我。</p>
        <p className="muted">遇到危机时，请拨打全国心理援助热线 12356，紧急情况拨打 120。</p>
      </div>
    </div>
  );
}
