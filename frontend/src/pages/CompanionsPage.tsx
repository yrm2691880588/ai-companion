import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import AvatarCropper from "../components/AvatarCropper";
import Menu from "../components/Menu";
import Modal from "../components/Modal";
import { downloadPersona } from "../components/PersonaImport";
import type { Companion, Latest } from "../types";

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("请选择图片文件"));
      return;
    }
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("图片读取失败"));
    };
    image.src = url;
  });
}

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
  const navigate = useNavigate();
  const [deleteTarget, setDeleteTarget] = useState<Companion | null>(null);
  const [deleteName, setDeleteName] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [avatarTarget, setAvatarTarget] = useState<number | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [cropFile, setCropFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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

  function pickAvatar(id: number) {
    setAvatarTarget(id);
    fileInputRef.current?.click();
  }

  async function onAvatarFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !avatarTarget) return;
    setAvatarBusy(true);
    setError("");
    try {
      // 先打开裁剪器，确认后再上传；这里只校验图片可读
      await loadImage(file);
      setCropFile(file);
    } catch (err) {
      setError((err as Error).message);
      setAvatarTarget(null);
    } finally {
      setAvatarBusy(false);
    }
  }

  async function saveCroppedAvatar(dataUrl: string) {
    if (!avatarTarget) return;
    try {
      const updated = await api.setAvatar(avatarTarget, dataUrl);
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCropFile(null);
      setAvatarTarget(null);
    }
  }

  async function clearAvatar(item: Companion) {
    try {
      const updated = await api.setAvatar(item.id, null);
      setItems((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      setMenuId(null);
    } catch (err) {
      setError((err as Error).message);
    }
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
                  <div
                    className="avatar avatar-editable"
                    title="点击更换头像"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      pickAvatar(item.id);
                    }}
                  >
                    {item.avatar ? (
                      <img src={item.avatar} alt={`${item.name} 的头像`} />
                    ) : (
                      item.persona.name.slice(0, 1)
                    )}
                    <span className="avatar-badge">{avatarBusy && avatarTarget === item.id ? "…" : "换"}</span>
                  </div>
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
                  <Menu
                    triggerLabel={`${item.name} 的更多操作`}
                    open={menuId === item.id}
                    onOpenChange={(open) => setMenuId(open ? item.id : null)}
                    trigger={
                      <button className="btn ghost" onClick={() => setMenuId(item.id)}>
                        更多
                      </button>
                    }
                    items={[
                      {
                        key: "persona",
                        label: "人设",
                        onSelect: () => navigate(`/companions/${item.id}/persona`),
                      },
                      {
                        key: "export",
                        label: "导出人设",
                        onSelect: () => downloadPersona(item),
                      },
                      {
                        key: "memories",
                        label: "记忆",
                        onSelect: () => navigate(`/companions/${item.id}/memories`),
                      },
                      {
                        key: "roleplay",
                        label: "演练",
                        onSelect: () => navigate(`/companions/${item.id}/roleplay`),
                      },
                      ...(item.avatar
                        ? [
                            {
                              key: "clear-avatar",
                              label: "清除头像",
                              onSelect: () => void clearAvatar(item),
                            },
                          ]
                        : []),
                      {
                        key: "delete",
                        label: "删除",
                        danger: true,
                        opensModal: true,
                        onSelect: () => askDelete(item),
                      },
                    ]}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        style={{ display: "none" }}
        onChange={(event) => void onAvatarFile(event)}
      />

      <AvatarCropper
        file={cropFile}
        onCancel={() => {
          setCropFile(null);
          setAvatarTarget(null);
        }}
        onSave={(dataUrl) => void saveCroppedAvatar(dataUrl)}
      />

      {deleteTarget && (
        <Modal
          open
          onClose={() => !deleting && setDeleteTarget(null)}
          title={`删除「${deleteTarget.name}」`}
          description="会一并删除她的会话、记忆与演练记录，且不可恢复。请输入名字确认："
          preventClose={deleting}
          footer={
            <>
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
            </>
          }
        >
          <input
            value={deleteName}
            autoFocus
            placeholder={deleteTarget.name}
            onChange={(event) => setDeleteName(event.target.value)}
          />
        </Modal>
      )}
    </div>
  );
}






