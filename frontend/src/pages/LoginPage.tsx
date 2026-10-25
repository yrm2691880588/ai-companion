import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

export default function LoginPage() {
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [debugCode, setDebugCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function sendCode() {
    setError("");
    setBusy(true);
    try {
      const result = await api.smsCode(phone.trim());
      setDebugCode(result.debug_code ?? null);
      if (!result.debug_code) setDebugCode(null);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setError("");
    setBusy(true);
    try {
      await api.login(phone.trim(), code.trim());
      navigate("/");
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 420, margin: "40px auto" }}>
      <h1>登录</h1>
      <p className="muted">用手机号 + 验证码登录；开发模式下验证码会直接显示，不会真的发短信。</p>

      {error && <div className="alert">{error}</div>}

      <div className="card">
        <label htmlFor="phone">手机号</label>
        <input
          id="phone"
          inputMode="numeric"
          value={phone}
          placeholder="13800001234"
          onChange={(event) => setPhone(event.target.value)}
        />
        <div className="composer" style={{ marginTop: 10 }}>
          <input
            value={code}
            inputMode="numeric"
            placeholder="6 位验证码"
            onChange={(event) => setCode(event.target.value)}
          />
          <button className="ghost" disabled={busy || phone.length !== 11} onClick={() => void sendCode()}>
            获取验证码
          </button>
        </div>
        {debugCode && <div className="notice">开发模式验证码：{debugCode}</div>}
        <div className="toolbar">
          <button
            className="primary"
            disabled={busy || phone.length !== 11 || code.length !== 6}
            onClick={() => void submit()}
          >
            {busy ? "处理中…" : "登录"}
          </button>
          <Link className="btn ghost" to="/">
            返回
          </Link>
        </div>
      </div>
    </div>
  );
}
