import React, { useState } from "react";
import ActionButton from "./ActionButton";
import { ArrowRight, Check, FlaskConical, Settings2 } from "lucide-react";
import { providerPresets } from "./providerPresets";

export default function ProviderForm({ existing, demo, busy, onSubmit }) {
  const initial = existing ? null : providerPresets[0];
  const [presetId, setPresetId] = useState(existing ? "custom" : initial.id);
  const [kind, setKind] = useState(
    existing?.provider_type || "openai_compatible",
  );
  const [name, setName] = useState(existing?.name || initial?.name || "");
  const [url, setUrl] = useState(existing?.base_url || initial?.baseUrl || "");
  const [model, setModel] = useState(
    existing?.chat_model || initial?.model || "",
  );
  const [secret, setSecret] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState(
    existing?.embedding_model || "",
  );
  const [consent, setConsent] = useState(false);
  const preset = providerPresets.find((p) => p.id === presetId);
  const isDemo = kind === "fake" || kind === "fake_files";
  const hasFiles = kind === "openai_files" || kind === "fake_files";

  function selectPreset(id) {
    if (id === presetId) return;
    const next = providerPresets.find((p) => p.id === id);
    setPresetId(id);
    setKind(id === "demo" ? "fake" : "openai_compatible");
    setName(next?.name || "");
    setUrl(next?.baseUrl || "");
    setModel(next?.model || "");
    setSecret("");
    setEmbeddingModel("");
    setConsent(false);
  }

  const settings = (
    <>
      {!existing && !preset && (
        <label>
          接口类型
          <select
            aria-label="接口类型"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setEmbeddingModel("");
              setConsent(false);
            }}
          >
            {presetId === "demo" ? (
              <>
                <option value="fake">离线演示（固定操作系统样例）</option>
                <option value="fake_files">
                  资料演示（固定样例，未读取上传内容）
                </option>
              </>
            ) : (
              <>
                <option value="openai_compatible">
                  OpenAI-compatible 聊天与图片接口（需检测）
                </option>
                <option value="openai_files">
                  原生 PDF（Files + Responses，需检测）
                </option>
              </>
            )}
          </select>
        </label>
      )}
      <label>
        连接名称
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如：我的学习模型"
          maxLength={100}
        />
      </label>
      {!isDemo && (
        <>
          <label>
            Base URL
            <input
              required
              type="url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setConsent(false);
              }}
              placeholder="https://你的服务商/v1"
            />
          </label>
          <label>
            聊天模型名称
            <input
              required
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="填写服务商提供的模型 ID"
              maxLength={200}
            />
          </label>
        </>
      )}
      {hasFiles && (
        <label>
          远端 Embedding 模型（可选）
          <input
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
            maxLength={200}
            placeholder="留空则按关键词检索，再由模型筛选"
          />
        </label>
      )}
    </>
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const body = {
          name: name || (isDemo ? "离线演示" : preset?.name || "我的模型"),
          chat_model: isDemo ? "demo-model" : model,
          embedding_model: embeddingModel || null,
          base_url: url || (isDemo ? "https://demo.invalid" : ""),
        };
        if (!existing) body.provider_type = kind;
        if (secret || !existing) body.api_key = isDemo ? "demo" : secret;
        onSubmit(body);
      }}
    >
      <span className="eyebrow">连接你选择的模型服务</span>
      <h2>{existing ? "更新模型连接" : "连接你的模型"}</h2>
      <p className="muted">
        {existing
          ? "凭证加密保存，所有教学调用使用你选择的模型。"
          : "选择供应商，填写 API Key，即可连接自己的学习模型。"}
      </p>
      {!existing && (
        <fieldset className="provider-presets">
          <legend>模型供应商</legend>
          <div className="provider-preset-grid">
            {providerPresets.map((p) => (
              <button
                key={p.id}
                type="button"
                className="provider-preset"
                aria-label={p.name}
                aria-pressed={presetId === p.id}
                onClick={() => selectPreset(p.id)}
              >
                <span>
                  <strong>{p.name}</strong>
                  <small>{p.description}</small>
                </span>
                {presetId === p.id && <Check size={16} aria-hidden="true" />}
              </button>
            ))}
            <button
              type="button"
              className="provider-preset"
              aria-label="自定义供应商"
              aria-pressed={presetId === "custom"}
              onClick={() => selectPreset("custom")}
            >
              <span>
                <strong>自定义供应商</strong>
                <small>自行填写接口与模型</small>
              </span>
              <Settings2 size={16} aria-hidden="true" />
            </button>
            {demo && (
              <button
                type="button"
                className="provider-preset"
                aria-label="离线演示"
                aria-pressed={presetId === "demo"}
                onClick={() => selectPreset("demo")}
              >
                <span>
                  <strong>离线演示</strong>
                  <small>无需 API Key · 固定样例</small>
                </span>
                <FlaskConical size={16} aria-hidden="true" />
              </button>
            )}
          </div>
        </fieldset>
      )}
      {preset ? (
        <div className="provider-preset-summary">
          <span>
            聊天模型：<strong>{model}</strong>
          </span>
          <code>{url}</code>
          <a href={preset.docsUrl} target="_blank" rel="noreferrer">
            供应商文档 ↗
          </a>
        </div>
      ) : (
        settings
      )}
      {!isDemo ? (
        <>
          <label>
            API Key
            <input
              required={!existing}
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={
                existing ? "留空保留当前密钥" : "粘贴所选供应商的 API Key"
              }
              autoComplete="new-password"
            />
          </label>
          <label className="checkbox">
            <input
              required
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              我授权将学习目标、教学上下文和答案发送至此服务商。
              图片能力检测会发送含随机标识的测试图片。
              {hasFiles && "文件能力检测会上传随机标识测试 PDF。"}
              调用可能产生费用，数据保留遵循其政策。
            </span>
          </label>
        </>
      ) : (
        <p className="hint">
          演示模式仅使用固定操作系统样例，不连接外部模型、不产生费用，不代表其他领域的真实教学结果。
        </p>
      )}
      {preset && (
        <details className="provider-advanced" key={presetId}>
          <summary>高级设置</summary>
          {settings}
        </details>
      )}
      {!isDemo && (
        <p className="provider-test-hint">
          保存后请检测模型能力，聊天与图片会分别验证。上传 PDF
          请使用自定义供应商的原生文件接口。
        </p>
      )}
      <ActionButton
        className="primary full"
        disabled={!!busy}
        loading={!!busy}
        loadingText="正在保存模型连接…"
      >
        保存模型连接 <ArrowRight size={16} />
      </ActionButton>
    </form>
  );
}
