import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Companion, Latest } from "../types";

function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  const date = new Date(iso);
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

export default function CompanionsPage() {
  const [items, setItems] = useState<Companion[]>([]);
  const [latests, setLatests] = useState<Record<number, Latest>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [menuId, setMenuId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Companion | null>(null);
  const [deleteName, setDeleteName] = useState("");
  const [deleting, setDeleting] = useState(false);

  async function reload() {
    try {
      const list = await api.companions();
      setItems(list);
      const entries = await Promise.all(
        list.map(async (item) => [item.id, await api.latest(item.id)] as const),
      );
      setLatests(Object.fromEntries(entries));
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  function askDelete(item: Companion) {
    setMenuId(null);
    setDeleteTarget(item);
    setDeleteName("");
    setError("");
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    if (deleteName.trim() !== deleteTarget.name) {
      setError("名字不一致，未删除");
      return;
    }
    setDeleting(true);
    try {
      await api.deleteCompanion(deleteTarget.id, deleteTarget.name);
      setDeleteTarget(null);
      await reload();
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>我的伴侣</h1>
          <p className="muted">点一张卡就能继续上次的对话。</p>
        </div>
        <Link className="btn primary" to="/create">
          创建伴侣
        </Link>
      </div>

      {error && <div className="alert">{error}</div>}
      {loading ? (
        <div className="grid" style={{ marginTop: 16 }}>
          {[0, 1].map((key) => (
            <div className="card skeleton-card" key={key}>
              <div className="skeleton avatar" />
              <div className="skeleton-line" />
              <div className="skeleton-line short" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="card empty-card" style={{ marginTop: 16 }}>
          <h3>还没有伴侣</h3>
          <p className="muted">用一句话描述你想要的人，或从 5 类官方模板开始。</p>
          <Link className="btn primary" to="/create">
            去创建
          </Link>
        </div>
      ) : (
        <div className="grid companions" style={{ marginTop: 16 }}>
          {items.map((item) => {
            const latest = latests[item.id];
            const preview = latest?.content
              ? latest.role === "assistant"
                ? latest.content
                : `你：${latest.content}`
              : "还没聊过，打个招呼吧";
            return (
              <div className="card companion-card" key={item.id}>
                <Link className="card-main" to={`/companions/${item.id}/chat`}>
                  <div className="avatar">{item.persona.name.slice(0, 1)}</div>
                  <div className="card-info">
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <h3>{item.name}</h3>
                      <span className="muted">
                        {relativeTime(latest?.created_at || item.updated_at)}
                      </span>
                    </div>
                    <p className="muted">
                      {item.persona.relationship || item.persona.identity}
                    </p>
                    <p className="last-line">{preview}</p>
                  </div>
                </Link>
                <div className="card-actions">
                  <Link className="btn primary" to={`/companions/${item.id}/chat`}>
                    {latest?.content ? "继续聊" : "开始聊天"}
                  </Link>
                  <button
                    className="btn ghost"
                    onClick={() => setMenuId(menuId === item.id ? null : item.id)}
                  >
                    更多
                  </button>
                  {menuId === item.id && (
                    <div className="menu">
                      <Link to={`/companions/${item.id}/memories`}>记忆</Link>
                      <Link to={`/companions/${item.id}/roleplay`}>演练</Link>
                      <button className="link danger-text" onClick={() => askDelete(item)}>
                        删除
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {deleteTarget && (
        <div className="modal-backdrop" onClick={() => !deleting && setDeleteTarget(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h2>删除「{deleteTarget.name}」</h2>
            <p className="muted">
              会一并删除她的会话、记忆与演练记录，且不可恢复。请输入名字确认：
            </p>
            <input
              value={deleteName}
              autoFocus
              placeholder={deleteTarget.name}
              onChange={(event) => setDeleteName(event.target.value)}
            />
            <div className="toolbar">
              <button
                className="danger"
                disabled={deleting || deleteName.trim() !== deleteTarget.name}
                onClick={() => void confirmDelete()}
              >
                {deleting ? "删除中…" : "确认删除"}
              </button>
              <button className="ghost" disabled={deleting} onClick={() => setDeleteTarget(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
