import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "../api";
import AvatarCropper from "../components/AvatarCropper";
import BatchDeleteModal from "../components/BatchDeleteModal";
import Menu from "../components/Menu";
import Modal from "../components/Modal";
import { downloadPersona } from "../lib/persona-export";
import type { Companion } from "../lib/types";

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
  const client = useQueryClient();
  const listQuery = useQuery(queries.companions());
  const items = listQuery.data ?? [];
  const latestQueries = useQueries({ queries: items.map(item => queries.latest(item.id)) });
  const latests = Object.fromEntries(items.map((item, index) => [item.id, latestQueries[index].data]));
  const loading = listQuery.isPending;
  const loadError = listQuery.error?.message || latestQueries.find(query => query.error)?.error?.message;
  const [error, setError] = useState("");
  const [menuId, setMenuId] = useState<number | null>(null);
  const navigate = useNavigate();
  const [deleteTarget, setDeleteTarget] = useState<Companion | null>(null);
  const [deleteName, setDeleteName] = useState("");
  const [deleting, setDeleting] = useState(false);
  // 批量管理：进入后可勾选多个伴侣一次性删除
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);
  // 单批上限由后端给出，用于自动分批
  const [batchLimit, setBatchLimit] = useState(50);
  const [avatarTarget, setAvatarTarget] = useState<number | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [cropFile, setCropFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function updateCompanion(updated: Companion) {
    client.setQueryData(queries.companion(updated.id).queryKey, updated);
    client.setQueryData(queries.companions().queryKey, (old) => old?.map(item => item.id === updated.id ? updated : item));
  }

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
      updateCompanion(updated);
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
      updateCompanion(updated);
      setMenuId(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  /** 批量删除：一次确认删多个，超过单批上限时自动分批，返回后刷新并报告结果。 */
  async function confirmBatchDelete(confirmWord: string) {
    if (selectedIds.length === 0) return;
    const ids = [...selectedIds];
    // 后端单批上限 50；超过就分批，避免用户手工数着勾选
    const deleted: number[] = [];
    const failed: { id: number; reason: string }[] = [];
    for (let index = 0; index < ids.length; index += batchLimit) {
      const chunk = ids.slice(index, index + batchLimit);
      const result = await api.batchDeleteCompanions(chunk, confirmWord);
      deleted.push(...result.deleted);
      failed.push(...result.failed);
    }
    setBatchDeleteOpen(false);
    setSelectedIds([]);
    setBatchMode(false);
    for (const id of deleted) {
      client.removeQueries({ queryKey: queries.companion(id).queryKey });
      client.removeQueries({ queryKey: queries.latest(id).queryKey });
    }
    await client.invalidateQueries({ queryKey: queries.companions().queryKey });
    if (failed.length > 0) {
      toast.warning(
        `已删除 ${deleted.length} 个，${failed.length} 个失败：${failed[0].reason}`,
      );
    } else {
      toast.success(`已删除 ${deleted.length} 个伴侣`);
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
      client.removeQueries({ queryKey: queries.companion(deleteTarget.id).queryKey });
      client.removeQueries({ queryKey: queries.latest(deleteTarget.id).queryKey });
      await client.invalidateQueries({ queryKey: queries.companions().queryKey });
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
        <div className="row" style={{ gap: 8 }}>
          {items.length > 0 && (
            <button
              className="btn ghost"
              onClick={() => {
                setBatchMode(!batchMode);
                setSelectedIds([]);
                // 取一次后端上限，超过时自动分批
                void api
                  .batchDeleteRules()
                  .then((rules) => setBatchLimit(rules.max_batch))
                  .catch(() => undefined);
              }}
            >
              {batchMode ? "退出批量" : "批量管理"}
            </button>
          )}
          <Link className="btn primary" to="/create">
            创建伴侣
          </Link>
        </div>
      </div>

      {batchMode && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="row" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <strong>已选 {selectedIds.length} 个</strong>
            <button
              className="btn ghost"
              onClick={() =>
                setSelectedIds(
                  selectedIds.length === items.length ? [] : items.map((item) => item.id),
                )
              }
            >
              {selectedIds.length === items.length ? "取消全选" : "全选"}
            </button>
            <button
              className="btn ghost"
              disabled={selectedIds.length === 0}
              onClick={() => setBatchDeleteOpen(true)}
            >
              删除选中
            </button>
            <span className="muted" style={{ fontSize: 12 }}>
              点卡片上的方框选中；删除不可恢复
            </span>
          </div>
        </div>
      )}

      {(error || loadError) && <div className="alert">{error || loadError}</div>}
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
      ) : listQuery.isError ? null : items.length === 0 ? (
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
                {batchMode && (
                  <label
                    className="batch-check"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(item.id)}
                      onChange={(event) =>
                        setSelectedIds((prev) =>
                          event.target.checked
                            ? [...prev, item.id]
                            : prev.filter((id) => id !== item.id),
                        )
                      }
                      aria-label={`选择 ${item.name}`}
                    />
                  </label>
                )}
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

      {batchDeleteOpen && selectedIds.length > 0 && (
        <BatchDeleteModal
          key={selectedIds.join(",")}
          count={selectedIds.length}
          names={items.filter((item) => selectedIds.includes(item.id)).map((item) => item.name)}
          busy={deleting}
          onCancel={() => setBatchDeleteOpen(false)}
          onConfirm={async (word) => {
            setDeleting(true);
            try {
              await confirmBatchDelete(word);
            } finally {
              setDeleting(false);
            }
          }}
        />
      )}

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







