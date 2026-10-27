import type { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { voiceSchema } from "../lib/forms";
import FieldError from "./FieldError";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "../api";

const GUIDE_STEPS = [
  {
    title: "1. 登录火山引擎控制台",
    detail: "打开 console.volcengine.com，用手机号或账号登录。",
  },
  {
    title: "2. 开通语音技术",
    detail: "在控制台搜索「语音技术」或「豆包语音」，进入后按提示开通（有免费额度试）。",
  },
  {
    title: "3. 创建应用",
    detail: "在语音技术控制台里创建一个应用，勾选「语音合成」与「语音识别」两个能力。",
  },
  {
    title: "4. 复制 AppID 与 Access Token",
    detail: "应用详情里能看到 AppID 和一串 Access Token，两个都要复制下来。",
  },
  {
    title: "5. 回到这里粘贴保存",
    detail: "把 AppID 与 Token 填进下面的输入框，点保存，再点「测试连接」确认通了。",
  },
];

export default function VoiceSettingsCard() {
  const client = useQueryClient();
  const providersQuery = useQuery(queries.voiceProviders());
  const providers = providersQuery.data ?? [];
  const { register, handleSubmit, setValue, formState: { errors } } = useForm<z.infer<typeof voiceSchema>>({
    resolver: zodResolver(voiceSchema),
    values: { appId: providers.find(item => item.key === "volcengine")?.app_id ?? "", token: "", cluster: "" },
    resetOptions: { keepDirtyValues: true }, mode: "onBlur",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showGuide, setShowGuide] = useState(false);

  async function save({ appId, token, cluster }: z.infer<typeof voiceSchema>) {
    setBusy(true);
    setError("");
    try {
      await api.saveVoiceProvider("volcengine", {
        app_id: appId.trim(),
        token: token.trim() || undefined,
        cluster: cluster.trim() || undefined,
      });
      await client.invalidateQueries({ queryKey: queries.voiceProviders().queryKey });
      await client.invalidateQueries({ queryKey: queries.voices("volcengine").queryKey });
      setValue("token", "");
      toast.success("已保存，可以点「测试连接」验证", { id: "voice-saved" });
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function probe() {
    setBusy(true);
    setError("");
    try {
      const result = await api.probeVoiceProvider("volcengine");
      if (result.ok) {
        toast.success(`连接成功，拿到 ${result.voice_count ?? 0} 个音色`, { id: "voice-probe" });
      } else {
        toast.error("连接失败，检查 AppID 与 Token", { id: "voice-probe" });
      }
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const volc = providers.find((item) => item.key === "volcengine");

  return (
    <form className="card" style={{ marginTop: 12 }} noValidate onSubmit={handleSubmit(save)}>
      <h2>语音</h2>
      <p className="muted">
        语音对话需要单独的供应商：你说话它识别成文字，她回复时合成语音。Key 只存在本机，加密保存。
      </p>

      {(error || providersQuery.error) && <div className="alert">{error || providersQuery.error?.message}</div>}

      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h3>火山引擎（豆包语音）</h3>
        <span className="chip">{volc?.configured ? "已配置" : "未配置"}</span>
      </div>

      <div className="field-grid">
        <div>
          <label htmlFor="voice-appid">AppID</label>
          <input
            id="voice-appid"
            {...register("appId")} aria-invalid={!!errors.appId} aria-describedby="voice-appId-error"
            placeholder="控制台里的 AppID"
          />
          <FieldError id="voice-appId-error" error={errors.appId} />
        </div>
        <div>
          <label htmlFor="voice-token">Access Token</label>
          <input
            id="voice-token"
            type="password"
            {...register("token")} aria-invalid={!!errors.token} aria-describedby="voice-token-error"
            placeholder={volc?.configured ? "留空则不修改" : "控制台里的 Access Token"}
          />
          <FieldError id="voice-token-error" error={errors.token} />
        </div>
        <div>
          <label htmlFor="voice-cluster">Cluster（可选）</label>
          <input
            id="voice-cluster"
            {...register("cluster")} aria-invalid={!!errors.cluster} aria-describedby="voice-cluster-error"
            placeholder="例如 volcano_tts"
          />
          <FieldError id="voice-cluster-error" error={errors.cluster} />
        </div>
      </div>

      <div className="toolbar">
        <button type="submit" className="primary" disabled={busy || providersQuery.isPending || providersQuery.isError}>
          {busy ? "保存中…" : "保存"}
        </button>
        <button type="button" className="ghost" disabled={busy || !volc?.configured} onClick={() => void probe()}>
          测试连接
        </button>
        <button type="button" className="ghost" onClick={() => setShowGuide(!showGuide)}>
          {showGuide ? "收起教程" : "怎么拿到 AppID 和 Token？"}
        </button>
        <a
          className="btn ghost"
          href="https://console.volcengine.com/speech/app"
          target="_blank"
          rel="noreferrer"
        >
          打开火山控制台
        </a>
      </div>

      {showGuide && (
        <div className="notice" style={{ marginTop: 10 }}>
          <ol style={{ paddingLeft: 20 }}>
            {GUIDE_STEPS.map((step) => (
              <li key={step.title} style={{ marginBottom: 8 }}>
                <strong>{step.title}</strong>
                <div className="muted">{step.detail}</div>
              </li>
            ))}
          </ol>
          <p className="muted">
            提示：开通语音服务可能产生费用，按你的实际用量由火山计费；本产品不代收、不加价。
          </p>
        </div>
      )}
    </form>
  );
}

