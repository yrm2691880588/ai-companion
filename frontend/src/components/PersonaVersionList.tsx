import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { History, RotateCcw } from "lucide-react";
import { queries } from "../lib/queries";
import { api } from "../api";
import Modal from "./Modal";
import Loading from "./Loading";
import ErrorAlert from "./ErrorAlert";
import { explainErrorText } from "../lib/errors";
import { relativeTime } from "../lib/format";
import { MAX_PERSONA_VERSIONS } from "../lib/constants";
import type { Companion, PersonaVersion } from "../lib/types";

interface Props {
  companionId: number;
  currentVersion: number;
  /** 还原成功后把新的伴侣记录交给上层刷新缓存。 */
  onRestored: (updated: Companion) => void;
}

/**
 * 人设版本历史。
 *
 * 为什么要有：改成「原地保存」之后，用户最大的担心是「改坏了回不去」。
 * 版本列表解决这个问题：任何一次保存都留着，随时可以还原。
 *
 * 还原的行为：把旧版本的内容**复制成一个新版本**，而不是把指针拨回去。
 * 这样「还原」本身也是可撤销的——还原之后还能再还原回来。
 */
export default function PersonaVersionList({ companionId, currentVersion, onRestored }: Props) {
  const client = useQueryClient();
  const versionsQuery = useQuery(queries.personaVersions(companionId));
  const versions = versionsQuery.data ?? [];
  const [target, setTarget] = useState<PersonaVersion | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function restore() {
    if (!target) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.restorePersonaVersion(companionId, target.version);
      client.setQueryData(queries.companion(companionId).queryKey, updated);
      await client.invalidateQueries({ queryKey: queries.personaVersions(companionId).queryKey });
      onRestored(updated);
      toast.success(`已还原到第 ${target.version} 版，现在是第 ${updated.current_version} 版`, {
        id: "persona-restored",
      });
      setTarget(null);
    } catch (event) {
      setError(explainErrorText(event));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <h2>
        <History size={16} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 6 }} />
        历史版本
      </h2>
      <p className="muted">
        每次保存都会留一个版本，最多保留最近 {MAX_PERSONA_VERSIONS} 个。还原不会删除任何记录。
      </p>

      <ErrorAlert message={error} variant="inline" onDismiss={() => setError("")} />

      {versionsQuery.isPending ? (
        <Loading lines={2} label="加载版本" />
      ) : versionsQuery.isError ? (
        <ErrorAlert
          message={versionsQuery.error.message}
          variant="inline"
          onRetry={() => void versionsQuery.refetch()}
        />
      ) : versions.length <= 1 ? (
        <p className="muted">还没有历史版本，改动并保存后这里会出现记录。</p>
      ) : (
        <ul className="version-list">
          {versions.map((item) => {
            const isCurrent = item.version === currentVersion;
            return (
              <li className={`version-item${isCurrent ? " current" : ""}`} key={item.version}>
                <div className="version-meta">
                  <strong>第 {item.version} 版</strong>
                  {isCurrent && <span className="chip">当前</span>}
                  <span className="muted">{relativeTime(item.created_at)}</span>
                </div>
                <p className="version-preview">
                  {item.persona.speaking_style || item.persona.background || "（无描述）"}
                </p>
                {!isCurrent && (
                  <button
                    className="btn ghost version-restore"
                    onClick={() => setTarget(item)}
                  >
                    <RotateCcw size={13} aria-hidden="true" />
                    还原到这版
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {target && (
        <Modal
          open
          onClose={() => !busy && setTarget(null)}
          title={`还原到第 ${target.version} 版？`}
          description="会用那一版的内容生成一个新版本，当前的版本和之后的所有改动都仍然保留，随时可以再还原回来。"
          preventClose={busy}
          footer={
            <>
              <button className="btn primary" disabled={busy} onClick={() => void restore()}>
                {busy ? "还原中…" : "确认还原"}
              </button>
              <button className="btn ghost" disabled={busy} onClick={() => setTarget(null)}>
                取消
              </button>
            </>
          }
        >
          <div className="refine-preview">
            {target.persona.speaking_style || target.persona.background || "（无描述）"}
          </div>
        </Modal>
      )}
    </div>
  );
}
