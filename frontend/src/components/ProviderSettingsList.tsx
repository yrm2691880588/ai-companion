import type { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { providerSchema } from "../lib/forms";
import FieldError from "./FieldError";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import Modal from "./Modal";
import type { DiscoveredModel, Provider } from "../lib/types";
import { explainErrorText } from "../lib/errors";
import ErrorAlert from "./ErrorAlert";

interface Props {
  providers: Provider[];
}

export default function ProviderSettingsList({ providers }: Props) {
  const client = useQueryClient();
  const settingsQuery = useQuery(queries.providerSettings());
  const settings = Object.fromEntries((settingsQuery.data ?? []).map(item => [item.provider_key, item]));
  const [editing, setEditing] = useState<string | null>(null);
  const { register, reset, handleSubmit, formState: { errors } } = useForm<z.infer<typeof providerSchema>>({
    resolver: zodResolver(providerSchema), defaultValues: { apiKey: "", baseUrl: "", enabled: true }, mode: "onBlur",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [discovered, setDiscovered] = useState<DiscoveredModel[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState("");
  const [probeResult, setProbeResult] = useState("");

  async function refreshSettings() {
    await Promise.all([
      client.invalidateQueries({ queryKey: queries.providerSettings().queryKey }),
      client.invalidateQueries({ queryKey: queries.providers().queryKey }),
      client.invalidateQueries({ queryKey: queries.admin().queryKey }),
    ]);
  }

  function startEdit(provider: Provider) {
    const setting = settings[provider.key];
    setEditing(provider.key);
    setDiscovered([]);
    setDiscoverError("");
    setProbeResult("");
    reset({ apiKey: "", baseUrl: setting?.base_url ?? provider.base_url, enabled: setting?.enabled ?? true });
    setError("");
  }

  async function save({ apiKey, baseUrl, enabled }: z.infer<typeof providerSchema>) {
    if (!editing) return;
    setBusy(true);
    setError("");
    try {
      await api.saveProviderSetting(editing, {
        api_key: apiKey.trim() ? apiKey.trim() : undefined,
        base_url: baseUrl.trim() || null,
        enabled,
      });
      await refreshSettings();
      setEditing(null);
      toast.success("已保存，立即生效", { id: "provider-saved" });
    } catch (event) {
      setError(explainErrorText(event));
    } finally {
      setBusy(false);
    }
  }

  async function probe() {
    if (!editing) return;
    setProbeResult("测试中…");
    try {
      const result = await api.probeProvider(editing);
      setProbeResult(result.ok ? `连接成功，可用模型 ${result.model_count} 个` : "连接失败");
    } catch (event) {
      setProbeResult((event as Error).message);
    }
  }

  async function importAll() {
    if (!editing || discovered.length === 0) return;
    setDiscovering(true);
    try {
      await api.importModels(
        editing,
        discovered.map((model) => model.id),
      );
      await refreshSettings();
      toast.success("已加入模型列表，可在上方下拉中选择", { id: "models-imported" });
    } catch (event) {
      setDiscoverError((event as Error).message);
    } finally {
      setDiscovering(false);
    }
  }

  async function discover() {
    if (!editing) return;
    setDiscovering(true);
    setDiscoverError("");
    try {
      setDiscovered(await api.discoverModels(editing));
    } catch (event) {
      setDiscoverError((event as Error).message);
      setDiscovered([]);
    } finally {
      setDiscovering(false);
    }
  }

  async function clearKey(providerKey: string) {
    setBusy(true);
    try {
      await api.saveProviderSetting(providerKey, { api_key: "" });
      await refreshSettings();
    } catch (event) {
      setError(explainErrorText(event));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <ErrorAlert message={error || settingsQuery.error?.message} variant="inline" />
      <p className="muted">
        点击「配置」填写 API Key 与地址。Key 只保存在本机，加密存储，不会显示明文。
      </p>
      <div className="grid provider-grid">
        {providers.map((provider) => {
          const setting = settings[provider.key];
          const hasKey = setting?.has_key ?? provider.has_key;
          const masked = setting?.masked_key ?? provider.masked_key;
          const address = setting?.base_url || provider.base_url;
          return (
            <div className="card provider-card" key={provider.key}>
              {/* 头部：名字 + 状态。状态用圆点和底色区分，
                  原来「已配置/未配置」都是同一个灰胶囊，看不出差别。 */}
              <div className="provider-head">
                <h3>{provider.name}</h3>
                <span className={`provider-status${hasKey ? " ready" : ""}`}>
                  <span className="provider-dot" aria-hidden="true" />
                  {hasKey ? "已配置" : "未配置"}
                </span>
              </div>

              {/* 中部：地址与 Key 状态。地址降为小字等宽，不再抢占视觉。 */}
              <p className="provider-address" title={address}>
                {address}
              </p>
              <p className="provider-meta">
                {provider.models.length} 个模型
                {hasKey ? ` · ${masked}` : " · 需要 API Key"}
              </p>

              {/* 模型标签：固定最多显示 3 个，其余折叠成 +N */}
              <div className="provider-models">
                {provider.models.slice(0, 3).map((model) => (
                  <span className="tag" key={model.key}>
                    {model.model_name}
                  </span>
                ))}
                {provider.models.length > 3 && (
                  <span className="tag more">+{provider.models.length - 3}</span>
                )}
              </div>

              {/* 底部：主操作与次要操作分开。
                  「清除 Key」是危险操作，不该和「配置」同样醒目。 */}
              <div className="provider-actions">
                <button className="btn primary" onClick={() => startEdit(provider)}>
                  {hasKey ? "修改配置" : "配置 Key"}
                </button>
                {hasKey && (
                  <button
                    className="link danger-text"
                    disabled={busy}
                    onClick={() => void clearKey(provider.key)}
                  >
                    清除 Key
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {editing && (
        <Modal
          open
          onClose={() => !busy && setEditing(null)}
          title="配置供应商"
          description="只保存在本机；保存后立即生效，不需要重启。"
          preventClose={busy}
          footer={
            <>
              <button className="primary" disabled={busy} type="submit" form="provider-settings">
                {busy ? "保存中…" : "保存"}
              </button>
              <button className="ghost" disabled={busy} onClick={() => setEditing(null)}>
                取消
              </button>
            </>
          }
        >
          <form id="provider-settings" noValidate onSubmit={handleSubmit(save)}>
          <ErrorAlert message={error || settingsQuery.error?.message} variant="inline" />
          <label htmlFor="provider-key">API Key</label>
          <input
            id="provider-key"
            {...register("apiKey")} aria-invalid={!!errors.apiKey} aria-describedby="provider-apiKey-error"
            placeholder="留空则不修改现有 Key"
          />
          <FieldError id="provider-apiKey-error" error={errors.apiKey} />
          <div className="toolbar" style={{ marginTop: 8 }}>
            <button type="button" className="ghost" disabled={discovering} onClick={() => void discover()}>
              {discovering ? "搜索中…" : "搜索该供应商的可用模型"}
            </button>
            <button type="button" className="ghost" onClick={() => void probe()}>
              测试连接
            </button>
          </div>
          {probeResult && <div className="notice">{probeResult}</div>}
          <ErrorAlert message={discoverError} variant="inline" />
          {discovered.length > 0 && (
            <div className="discovered">
              <p className="muted">
                找到 {discovered.length} 个模型（点击下方按钮加入本机模型列表）：
              </p>
              <div>
                {discovered.map((model) => (
                  <span className="tag" key={model.id} title={model.owned_by}>
                    {model.id}
                  </span>
                ))}
              </div>
              <div className="toolbar">
                <button type="button" className="primary" disabled={discovering} onClick={() => void importAll()}>
                  全部加入模型列表
                </button>
              </div>
            </div>
          )}

          <label htmlFor="provider-url">Base URL</label>
          <input
            id="provider-url"
            {...register("baseUrl")} aria-invalid={!!errors.baseUrl} aria-describedby="provider-baseUrl-error"
            placeholder="https://api.example.com/v1"
          />
          <FieldError id="provider-baseUrl-error" error={errors.baseUrl} />
          <label className="muted" style={{ display: "block", marginTop: 10 }}>
            <input
              type="checkbox"
              {...register("enabled")}
            />{" "}
            启用这个供应商
          </label>
          </form>
        </Modal>
      )}
    </div>
  );
}





