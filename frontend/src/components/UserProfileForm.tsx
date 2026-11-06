import { useForm } from "react-hook-form";
import type { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { profileSchema, nullableNumber } from "../lib/forms";
import FieldError from "./FieldError";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import type { UserProfile } from "../lib/types";
import { explainErrorText } from "../lib/errors";

interface Props {
  companionId?: number;
  title: string;
  description: string;
}

const EMPTY: UserProfile = {
  nickname: "",
  identity: "",
  age: null,
  gender: "",
  city: "",
  background: "",
};

export default function UserProfileForm({ companionId, title, description }: Props) {
  const client = useQueryClient();
  const profileQuery = useQuery({ ...queries.profile(), enabled: !companionId });
  const companionProfileQuery = useQuery({ ...queries.companionProfile(companionId ?? 0), enabled: !!companionId });
  const data = companionId ? companionProfileQuery.data : profileQuery.data;
  const value: z.infer<typeof profileSchema> = {
    nickname: data?.nickname ?? EMPTY.nickname, identity: data?.identity ?? EMPTY.identity,
    age: data?.age ?? null, gender: data?.gender ?? EMPTY.gender,
    city: data?.city ?? EMPTY.city, background: data?.background ?? EMPTY.background,
  };
  const loadError = profileQuery.error?.message || companionProfileQuery.error?.message;
  const loading = companionId ? companionProfileQuery.isPending : profileQuery.isPending;
  const { register, handleSubmit, formState: { errors, isSubmitting: busy } } = useForm<z.infer<typeof profileSchema>>({
    resolver: zodResolver(profileSchema), values: value, resetOptions: { keepDirtyValues: true }, mode: "onBlur",
  });
  const [error, setError] = useState("");

  async function save(value: UserProfile) {
    setError("");
    try {
      if (companionId) {
        const saved = await api.saveCompanionProfile(companionId, {
          nickname: value.nickname || null,
          identity: value.identity || null,
          age: value.age,
          gender: value.gender || null,
          city: value.city || null,
          background: value.background || null,
        });
        client.setQueryData(queries.companionProfile(companionId).queryKey, saved);
      } else {
        const saved = await api.saveProfile(value);
        client.setQueryData(queries.profile().queryKey, saved);
      }
      toast.success("已保存，下一条回复生效", { id: "profile-saved" });
    } catch (event) {
      setError(explainErrorText(event));
    }
  }

  return (
    <form className="card" noValidate onSubmit={handleSubmit(save)}>
      <h2>{title}</h2>
      <p className="muted">{description}</p>
      {(error || loadError) && <div className="alert">{error || loadError}</div>}
      <div className="field-grid">
        <div>
          <label htmlFor={`up-nick-${companionId ?? "me"}`}>她怎么称呼你</label>
          <input
            id={`up-nick-${companionId ?? "me"}`}
            {...register("nickname")} aria-invalid={!!errors.nickname} aria-describedby={`profile-nickname-${companionId ?? "me"}-error`}
            placeholder="小周 / 周哥 / 宝宝"
          />
          <FieldError id={`profile-nickname-${companionId ?? "me"}-error`} error={errors.nickname} />
        </div>
        <div>
          <label htmlFor={`up-identity-${companionId ?? "me"}`}>你的身份</label>
          <input
            id={`up-identity-${companionId ?? "me"}`}
            {...register("identity")} aria-invalid={!!errors.identity} aria-describedby={`profile-identity-${companionId ?? "me"}-error`}
            placeholder="大三学生 / 后端工程师"
          />
          <FieldError id={`profile-identity-${companionId ?? "me"}-error`} error={errors.identity} />
        </div>
        <div>
          <label htmlFor={`up-age-${companionId ?? "me"}`}>年龄</label>
          <input
            id={`up-age-${companionId ?? "me"}`}
            type="number"
            min={18}
            max={99}
            {...register("age", { setValueAs: nullableNumber })} aria-invalid={!!errors.age} aria-describedby={`profile-age-${companionId ?? "me"}-error`}
          />
          <FieldError id={`profile-age-${companionId ?? "me"}-error`} error={errors.age} />
        </div>
        <div>
          <label htmlFor={`up-city-${companionId ?? "me"}`}>城市</label>
          <input
            id={`up-city-${companionId ?? "me"}`}
            {...register("city")} aria-invalid={!!errors.city} aria-describedby={`profile-city-${companionId ?? "me"}-error`}
            placeholder="杭州"
          />
          <FieldError id={`profile-city-${companionId ?? "me"}-error`} error={errors.city} />
        </div>
      </div>
      <label htmlFor={`up-background-${companionId ?? "me"}`}>补充背景</label>
      <textarea
        id={`up-background-${companionId ?? "me"}`}
        {...register("background")} aria-invalid={!!errors.background} aria-describedby={`profile-background-${companionId ?? "me"}-error`}
        placeholder="最近在准备考研，晚上常熬夜；不喜欢被叫全名。"
      />
          <FieldError id={`profile-background-${companionId ?? "me"}-error`} error={errors.background} />
      <div className="toolbar">
        <button className="primary" disabled={busy || loading || !!loadError} type="submit">
          {busy ? "保存中…" : "保存"}
        </button>
      </div>
    </form>
  );
}

