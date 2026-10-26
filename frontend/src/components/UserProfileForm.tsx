import { useEffect, useState } from "react";
import { api } from "../api";
import type { UserProfile } from "../types";

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
  const [value, setValue] = useState<UserProfile>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        if (companionId) {
          const data = await api.getCompanionProfile(companionId);
          setValue({
            nickname: data.nickname ?? "",
            identity: data.identity ?? "",
            age: data.age ?? null,
            gender: data.gender ?? "",
            city: data.city ?? "",
            background: data.background ?? "",
          });
        } else {
          setValue(await api.getProfile());
        }
      } catch (event) {
        setError((event as Error).message);
      }
    })();
  }, [companionId]);

  function update<K extends keyof UserProfile>(key: K, next: UserProfile[K]) {
    setValue((prev) => ({ ...prev, [key]: next }));
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      if (companionId) {
        await api.saveCompanionProfile(companionId, {
          nickname: value.nickname || null,
          identity: value.identity || null,
          age: value.age,
          gender: value.gender || null,
          city: value.city || null,
          background: value.background || null,
        });
      } else {
        await api.saveProfile(value);
      }
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>{title}</h2>
      <p className="muted">{description}</p>
      {error && <div className="alert">{error}</div>}
      <div className="field-grid">
        <div>
          <label htmlFor={`up-nick-${companionId ?? "me"}`}>她怎么称呼你</label>
          <input
            id={`up-nick-${companionId ?? "me"}`}
            value={value.nickname}
            placeholder="小周 / 周哥 / 宝宝"
            onChange={(event) => update("nickname", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={`up-identity-${companionId ?? "me"}`}>你的身份</label>
          <input
            id={`up-identity-${companionId ?? "me"}`}
            value={value.identity}
            placeholder="大三学生 / 后端工程师"
            onChange={(event) => update("identity", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={`up-age-${companionId ?? "me"}`}>年龄</label>
          <input
            id={`up-age-${companionId ?? "me"}`}
            type="number"
            min={18}
            max={99}
            value={value.age ?? ""}
            onChange={(event) =>
              update("age", event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </div>
        <div>
          <label htmlFor={`up-city-${companionId ?? "me"}`}>城市</label>
          <input
            id={`up-city-${companionId ?? "me"}`}
            value={value.city}
            placeholder="杭州"
            onChange={(event) => update("city", event.target.value)}
          />
        </div>
      </div>
      <label htmlFor={`up-background-${companionId ?? "me"}`}>补充背景</label>
      <textarea
        id={`up-background-${companionId ?? "me"}`}
        value={value.background}
        placeholder="最近在准备考研，晚上常熬夜；不喜欢被叫全名。"
        onChange={(event) => update("background", event.target.value)}
      />
      <div className="toolbar">
        <button className="primary" disabled={busy} onClick={() => void save()}>
          {busy ? "保存中…" : "保存"}
        </button>
        {saved && <span className="muted">已保存，下一条回复生效</span>}
      </div>
    </div>
  );
}
