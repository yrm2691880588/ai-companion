import { useState } from "react";
import { Sparkles, Wand2 } from "lucide-react";
import { api } from "../api";
import Modal from "./Modal";
import { explainErrorText } from "../lib/errors";
import { MAX_REFINE_HINT } from "../lib/constants";
import type { Persona } from "../lib/types";
import ErrorAlert from "./ErrorAlert";

interface Props {
  /** 当前整份人设草稿，作为改写的上下文（不落库）。 */
  persona: Persona;
  /** 要改的维度 key，例如 background / speaking_style。 */
  dimension: string;
  /** 这个维度在界面上的中文名，用于文案。 */
  label: string;
  /** 用户点「采用」时回调，把新值交给表单。 */
  onApply: (value: unknown) => void;
}

/** 快捷要求：覆盖大多数「想改但说不清」的情况。 */
const QUICK_HINTS = [
  { label: "更简短", hint: "压缩到两句话以内，去掉冗余细节" },
  { label: "更具体", hint: "补充具体的细节、场景和数字，不要空泛" },
  { label: "换个方向", hint: "换一个完全不同的角度重新写" },
  { label: "加点反差", hint: "加入一点和表面性格相反的特质，让人物更立体" },
  { label: "更口语", hint: "写得更口语化，像日常说话而不是书面描述" },
];

/**
 * 单个字段的「AI 帮我改」。
 *
 * 为什么需要它：用户经常知道「这块不对劲」，但说不清该怎么改。
 * 让用户用自己的话描述，AI 生成建议值，用户看过再决定采不采用。
 *
 * 关键设计：**生成后先预览，点「采用」才写回表单**。
 * 直接覆盖会让用户丢掉原本满意的内容，也没法对比。
 */
export default function PersonaRefineButton({ persona, dimension, label, onApply }: Props) {
  const [open, setOpen] = useState(false);
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  /** 生成出来的建议值；有值时界面切到「预览」态。 */
  const [suggestion, setSuggestion] = useState<unknown>(null);
  const [cost, setCost] = useState<number | null>(null);

  function reset() {
    setHint("");
    setError("");
    setSuggestion(null);
    setCost(null);
    setBusy(false);
  }

  function close() {
    if (busy) return;
    setOpen(false);
    reset();
  }

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const result = await api.refinePersonaDimension(persona, dimension, hint.trim() || null);
      setSuggestion(result.value);
      setCost(result.costCny);
    } catch (event) {
      setError(explainErrorText(event));
    } finally {
      setBusy(false);
    }
  }

  function apply() {
    onApply(suggestion);
    setOpen(false);
    reset();
  }

  /** 建议值可能是字符串也可能是数组，统一转成可读文本。 */
  function renderValue(value: unknown): string {
    if (Array.isArray(value)) return value.join("、");
    if (value === null || value === undefined) return "";
    return String(value);
  }

  const hasSuggestion = suggestion !== null;

  return (
    <>
      <button
        type="button"
        className="refine-btn"
        onClick={() => setOpen(true)}
        title={`让 AI 帮你改「${label}」`}
      >
        <Sparkles size={13} aria-hidden="true" />
        AI 帮我改
      </button>

      {open && (
        <Modal
          open
          onClose={close}
          title={hasSuggestion ? `「${label}」的新版本` : `AI 帮你改「${label}」`}
          description={
            hasSuggestion
              ? "看一下像不像你要的感觉；不满意可以再生成一次。"
              : "用你自己的话说想怎么改，说不清就点下面的快捷选项。"
          }
          preventClose={busy}
          footer={
            hasSuggestion ? (
              <>
                <button className="primary" onClick={apply} disabled={busy}>
                  <Wand2 size={15} aria-hidden="true" />
                  采用这版
                </button>
                <button className="ghost" onClick={() => void generate()} disabled={busy}>
                  {busy ? "重新生成中…" : "再生成一次"}
                </button>
                <button className="ghost" onClick={close} disabled={busy}>
                  放弃
                </button>
              </>
            ) : (
              <>
                <button className="primary" onClick={() => void generate()} disabled={busy}>
                  {busy ? "生成中…" : "生成一版看看"}
                </button>
                <button className="ghost" onClick={close} disabled={busy}>
                  取消
                </button>
              </>
            )
          }
        >
          {error && <ErrorAlert message={error} variant="inline" />}

          {!hasSuggestion && (
            <>
              <label htmlFor="refine-hint">你想怎么改？</label>
              <textarea
                id="refine-hint"
                value={hint}
                maxLength={MAX_REFINE_HINT}
                placeholder="例如：太长了，帮我压到两句话；或者：加点她打游戏时的具体细节"
                onChange={(event) => setHint(event.target.value)}
              />
              <div className="refine-quick">
                {QUICK_HINTS.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    className="chip-button"
                    onClick={() => setHint(item.hint)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </>
          )}

          {hasSuggestion && (
            <>
              <div className="refine-preview">{renderValue(suggestion)}</div>
              {cost !== null && cost > 0 && (
                <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                  本次生成花费约 ¥{cost.toFixed(4)}
                </p>
              )}
            </>
          )}
        </Modal>
      )}
    </>
  );
}
