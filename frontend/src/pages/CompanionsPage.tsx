import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Companion } from "../types";

export default function CompanionsPage() {
  const [items, setItems] = useState<Companion[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function reload() {
    try {
      setItems(await api.companions());
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  async function remove(item: Companion) {
    const typed = window.prompt(
      `删除「${item.name}」会一并删除会话、记忆与演练记录，且不可恢复。\n请输入名字确认：`,
    );
    if (typed === null) return;
    if (typed.trim() !== item.name) {
      window.alert("名字不一致，未删除");
      return;
    }
    try {
      await api.deleteCompanion(item.id, typed.trim());
      await reload();
    } catch (event) {
      setError((event as Error).message);
    }
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>我的伴侣</h1>
          <p className="muted">创建后可以聊天、查看长期记忆、做场景演练。</p>
        </div>
        <Link className="btn primary" to="/create">
          创建伴侣
        </Link>
      </div>

      {error && <div className="alert">{error}</div>}
      {loading ? (
        <p className="muted">加载中…</p>
      ) : items.length === 0 ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>还没有伴侣</h3>
          <p className="muted">用一句话描述你想要的人，或从 5 类官方模板开始。</p>
          <Link className="btn primary" to="/create">
            去创建
          </Link>
        </div>
      ) : (
        <div className="grid" style={{ marginTop: 16 }}>
          {items.map((item) => (
            <div className="card" key={item.id}>
              <h3>{item.name}</h3>
              <p className="muted">
                {item.persona.identity} · 人设 v{item.current_version}
              </p>
              <div>
                {item.persona.tags.map((tag) => (
                  <span className="tag" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
              <div className="toolbar">
                <Link className="btn" to={`/companions/${item.id}/chat`}>
                  聊天
                </Link>
                <Link className="btn ghost" to={`/companions/${item.id}/memories`}>
                  记忆
                </Link>
                <Link className="btn ghost" to={`/companions/${item.id}/roleplay`}>
                  演练
                </Link>
                <button className="danger" onClick={() => void remove(item)}>
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
