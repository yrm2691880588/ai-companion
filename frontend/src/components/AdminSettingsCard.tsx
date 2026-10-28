import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { adminSchema } from "../lib/forms";
import FieldError from "./FieldError";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import type { AdminSettingsResponse } from "../lib/types";

export default function AdminSettingsCard() {
  const client = useQueryClient();
  const adminQuery = useQuery(queries.admin());
  if (!adminQuery.data) return <p className="muted">{adminQuery.error?.message || "加载管理员设置…"}</p>;
  return <AdminEditor admin={adminQuery.data} onSaved={saved => client.setQueryData(queries.admin().queryKey, saved)} />;
}

function AdminEditor({ admin, onSaved }: { admin: AdminSettingsResponse; onSaved: (saved: AdminSettingsResponse) => void }) {
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(adminSchema), values: { model_defaults: admin.settings.model_defaults },
    resetOptions: { keepDirtyValues: true }, mode: "onBlur",
  });
  const [error, setError] = useState("");

  async function save(data: { model_defaults: AdminSettingsResponse["settings"]["model_defaults"] }) {
    setError("");
    try {
      const saved = await api.adminUpdate({ model_defaults: data.model_defaults });
      onSaved(saved);
      reset({ model_defaults: saved.settings.model_defaults });
      toast.success("已保存", { id: "admin-saved" });
    } catch (event) {
      setError((event as Error).message);
    }
  }

  return (
    <form className="card" style={{ marginTop: 12 }} onSubmit={handleSubmit(save)}>
      <h2>模型参数</h2>
      <p className="muted">本机统一配置，保存后下一条回复生效。</p>
      {error && <div className="alert">{error}</div>}
      {(["chat_main", "persona_generate"] as const).map((task) => {
        const label = task === "chat_main" ? "日常对话" : "人设生成";
        return (
          <div key={task} style={{ marginTop: 14 }}>
            <h3>{label}</h3>
            <div className="admin-field-grid">
              <label className="admin-field wide">
                <span>模型</span>
                <select
                  {...register(`model_defaults.${task}.model`)}
                >
                  <option value="">跟随系统路由</option>
                  {admin.models.map((model) => (
                    <option key={model.key} value={model.key}>
                      {model.display_name}
                    </option>
                  ))}
                </select>
                <FieldError id={`admin-${task}-model-error`} error={errors.model_defaults?.[task]?.model} />
              </label>
              <label className="admin-field">
                <span>温度（0–2）</span>
                <input
                  type="number"
                  step="0.1"
                  min={0}
                  max={2}
                  {...register(`model_defaults.${task}.temperature`, { valueAsNumber: true })}
                />
                <FieldError id={`admin-${task}-temperature-error`} error={errors.model_defaults?.[task]?.temperature} />
              </label>
              <label className="admin-field">
                <span>top_p（0–1）</span>
                <input
                  type="number"
                  step="0.05"
                  min={0}
                  max={1}
                  {...register(`model_defaults.${task}.top_p`, { valueAsNumber: true })}
                />
                <FieldError id={`admin-${task}-top_p-error`} error={errors.model_defaults?.[task]?.top_p} />
              </label>
              <label className="admin-field wide">
                <span>最大输出（tokens，32–4096）</span>
                <input
                  type="number"
                  min={32}
                  max={4096}
                  {...register(`model_defaults.${task}.max_tokens`, { valueAsNumber: true })}
                />
                <FieldError id={`admin-${task}-max_tokens-error`} error={errors.model_defaults?.[task]?.max_tokens} />
              </label>
              <label className="admin-check">
                <input
                  type="checkbox"
                  {...register(`model_defaults.${task}.thinking`)}
                />
                <FieldError id={`admin-${task}-thinking-error`} error={errors.model_defaults?.[task]?.thinking} />
                <span>思考模式</span>
              </label>
            </div>
          </div>
        );
      })}

      <div className="toolbar">
        <button className="primary" type="submit" disabled={isSubmitting}>
          保存管理员设置
        </button>
      </div>
    </form>
  );
}


