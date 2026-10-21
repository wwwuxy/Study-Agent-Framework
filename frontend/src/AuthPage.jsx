import React, { useEffect, useState } from "react";
import ActionButton from "./ActionButton";
import { Layers, ArrowUpRight, ArrowRight, FlaskConical } from "lucide-react";
import { api } from "./api";

export default function AuthPage({ mode, onModeChange, onLogin, config }) {
  const register = mode === "register";
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    setPassword("");
    setConfirmPassword("");
    setError("");
  }, [mode]);
  return (
    <div className="auth-page">
      <section className="auth-story">
        <div className="brand">
          <span className="brand-icon">
            <Layers size={24} />
          </span>{" "}
          StudyAgent
        </div>
        <span className="eyebrow">围绕你的目标，按你的节奏学习</span>
        <h1>
          让每一步学习，
          <br />
          都有依据。
        </h1>
        <p>
          一个了解你的学习起点、记得你的进步，
          <br />
          并持续为你规划下一步的个人学习空间。
        </p>
        <div className="auth-visual">
          <span>01 / 确定目标</span>
          <span>02 / 发现起点</span>
          <span>
            03 / 循序向前 <ArrowUpRight size={20} />
          </span>
        </div>
        <small>自选模型 · 进度自动保存 · 作答记录可回看</small>
      </section>
      <section className="auth-form">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            if (register && password !== confirmPassword) {
              setError("两次输入的密码不一致，请重新输入。");
              return;
            }
            setBusy(true);
            try {
              const u = await api(
                "/auth/" + (register ? "register" : "login"),
                { method: "POST", body: { username, password } },
              );
              await onLogin(u);
            } catch (err) {
              setError(err.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <span className="eyebrow">
            {register
              ? "创建账号，开始积累学习进度"
              : "从上次的进度，走向下一步"}
          </span>
          <h2>{register ? "创建你的学习账号" : "欢迎回到学习空间"}</h2>
          <p className="muted">
            {register
              ? "从今天开始，积累属于你的进步。"
              : "接上昨天的思路，继续今天的进步。"}
          </p>
          <label>
            用户名
            <input
              required
              minLength={3}
              maxLength={64}
              pattern="[a-zA-Z0-9_\-]+"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="3–64 位字母、数字、下划线"
            />
          </label>
          <label>
            密码
            <input
              required
              type="password"
              minLength={10}
              maxLength={128}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={register ? "new-password" : "current-password"}
              placeholder="至少 10 位"
            />
          </label>
          {register && (
            <label>
              确认密码
              <input
                required
                type="password"
                minLength={10}
                maxLength={128}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="再次输入密码"
              />
            </label>
          )}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <ActionButton
            className="primary full"
            disabled={busy}
            loading={busy}
            loadingText={register ? "正在创建学习账号…" : "正在进入学习空间…"}
          >
            {register ? "创建账号" : "进入学习空间"} <ArrowRight size={17} />
          </ActionButton>
          <p className="auth-switch">
            {register ? "已有账号？" : "第一次来？"}{" "}
            <button
              type="button"
              className="text-button"
              onClick={() => {
                onModeChange(register ? "login" : "register");
                setConfirmPassword("");
                setError("");
              }}
            >
              {register ? "登录" : "创建账号"}
            </button>
          </p>
          {config.demo_enabled && (
            <span className="demo-hint">
              <FlaskConical size={14} /> 可使用离线样例体验学习流程，无需 API
              Key
            </span>
          )}
        </form>
      </section>
    </div>
  );
}
