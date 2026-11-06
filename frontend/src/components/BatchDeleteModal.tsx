import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "sonner";
import Modal from "./Modal";

interface Props {
  /** 已选中的伴侣数量 */
  count: number;
  /** 已选中的名字，用于确认提示 */
  names: string[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: (confirmWord: string) => Promise<void>;
}

/**
 * 批量删除确认弹窗。
 *
 * 保护强度与单个删除一致：必须手输「删除」两个字才能执行。
 * 不提供「一滑到底就删」的捷径，避免误删整库。
 *
 * 输入状态由父组件通过 key 重挂载来重置（本项目既有约定），
 * 不用 effect 里 setState，避免级联渲染。
 */
export default function BatchDeleteModal({
  count,
  names,
  busy,
  onCancel,
  onConfirm,
}: Props) {
  const [word, setWord] = useState("");
  const [error, setError] = useState("");
  // 确认词与上限由后端给出，避免前端复制业务常量（改一处漏另一处）
  const [confirmWord, setConfirmWord] = useState("");
  const [maxBatch, setMaxBatch] = useState(50);

  useEffect(() => {
    let active = true;
    void api
      .batchDeleteRules()
      .then((rules) => {
        if (!active) return;
        setConfirmWord(rules.confirm);
        setMaxBatch(rules.max_batch);
      })
      .catch(() => {
        // 规则拿不到时不阻断弹窗，按后端默认值兜底；提交仍由后端校验
      });
    return () => {
      active = false;
    };
  }, []);

  // confirmWord 为空说明规则还没拿到：此时按钮保持禁用，并显示加载中，
  // 避免用户输入了正确词却因为规则未到而点不动
  const rulesReady = confirmWord !== "";
  const ready = rulesReady && word.trim() === confirmWord;

  async function submit() {
    if (!ready) {
      setError(`请输入「${confirmWord}」确认`);
      return;
    }
    setError("");
    try {
      await onConfirm(word.trim());
    } catch (event) {
      setError((event as Error).message);
      toast.error((event as Error).message);
    }
  }

  const preview = names.slice(0, 5).join("、");
  const more = names.length > 5 ? ` 等 ${names.length} 个` : "";

  return (
    <Modal
      open
      onClose={() => !busy && onCancel()}
      title={`删除 ${count} 个伴侣`}
      description={`会一并删除她们的会话、记忆与演练记录，且不可恢复。一次最多 ${maxBatch} 个。`}
    >
      <p className="muted">
        将删除：{preview}
        {more}
      </p>
      <div style={{ marginTop: 12 }}>
        <label htmlFor="batch-confirm">
          {rulesReady ? `请输入「${confirmWord}」确认` : "正在读取确认规则…"}
        </label>
        <input
          id="batch-confirm"
          value={word}
          onChange={(event) => setWord(event.target.value)}
          placeholder={confirmWord || "加载中…"}
          disabled={!rulesReady}
          autoComplete="off"
        />
      </div>
      {error && <div className="alert" style={{ marginTop: 8 }}>{error}</div>}
      <div className="toolbar" style={{ marginTop: 14 }}>
        <button className="primary" disabled={busy || !ready} onClick={() => void submit()}>
          {!rulesReady ? "加载确认规则…" : busy ? "删除中…" : `确认删除 ${count} 个`}
        </button>
        <button className="ghost" disabled={busy} onClick={onCancel}>
          取消
        </button>
      </div>
    </Modal>
  );
}
