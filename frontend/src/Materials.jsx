import React, { useEffect, useRef, useState } from "react";
import { api, key } from "./api";

export function Citations({ sources = [], root }) {
  if (!sources.length) return null;
  return (
    <section className="citations">
      <h3>教材证据</h3>
      {sources.map((s) => (
        <article key={s.source_id}>
          <b>
            {s.filename} · {s.heading}
          </b>
          <p>{s.summary}</p>
          <small>
            {s.is_demo
              ? "固定演示资料 · 未读取上传内容"
              : "远端模型提取，仍需核实"}{" "}
            · 章节定位 · 页码未核实
          </small>
          <p>
            <a
              href={
                "/api/v1" +
                (root || "/study-spaces/" + s.study_space_id) +
                "/materials/" +
                s.document_id +
                "/download"
              }
            >
              下载原文核对
            </a>
          </p>
        </article>
      ))}
    </section>
  );
}

export default function Materials({
  root,
  provider,
  space,
  onRefresh,
  maxBytes,
}) {
  const [rows, setRows] = useState([]),
    [selected, setSelected] = useState(null),
    [file, setFile] = useState(null),
    [consent, setConsent] = useState(false),
    [embeddings, setEmbeddings] = useState(false),
    [query, setQuery] = useState(""),
    [mode, setMode] = useState("auto"),
    [results, setResults] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const alive = useRef(true),
    revision = useRef(0),
    readVersion = useRef(0),
    uploadKey = useRef(key()),
    refreshWorkspace = useRef(onRefresh),
    syncedVersion = useRef("");
  refreshWorkspace.current = onRefresh;
  const dataVersion = JSON.stringify(
    rows.map((row) => [row.id, row.status, row.job_id, row.job?.status]),
  );
  const canUpload =
    provider?.tested &&
    provider.capabilities.file_input &&
    provider.capabilities.supported_mime_types?.includes("application/pdf");
  useEffect(() => {
    setConsent(false);
    setEmbeddings(false);
    uploadKey.current = key();
  }, [provider?.id, provider?.chat_model, provider?.tested]);
  async function reload() {
    const ticket = ++readVersion.current;
    const data = await api(root + "/materials");
    if (alive.current && ticket === readVersion.current) setRows(data);
  }
  useEffect(() => {
    alive.current = true;
    reload().catch((e) => alive.current && setError(e.message));
    const timer = setInterval(() => reload().catch(() => {}), 3000);
    return () => {
      alive.current = false;
      revision.current++;
      readVersion.current++;
      clearInterval(timer);
    };
  }, [root]);
  useEffect(() => {
    let current = true;
    const selectedId = selected?.id;
    const row = rows.find((item) => item.id === selectedId);
    if (selectedId) {
      if (!row || row.status === "deleting") setSelected(null);
      else
        api(root + "/materials/" + selectedId)
          .then((detail) => current && setSelected(detail))
          .catch((e) => current && setError(e.message));
    }
    if (syncedVersion.current !== dataVersion)
      refreshWorkspace
        .current()
        .then(() => {
          if (current) syncedVersion.current = dataVersion;
        })
        .catch((e) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [root, dataVersion, selected?.id]);
  async function run(fn) {
    const ticket = ++revision.current;
    setBusy(true);
    setError("");
    const current = () => alive.current && revision.current === ticket;
    try {
      await fn(current);
    } catch (e) {
      if (current()) setError(e.message);
    } finally {
      if (current()) setBusy(false);
    }
  }
  function resetEvidence() {
    setSelected(null);
    setResults(null);
  }
  return (
    <>
      <div className="page-title">
        <span className="eyebrow">YOUR PRIVATE LIBRARY</span>
        <h1>私人教材</h1>
        <p>资料由你选择的远端模型理解。上传、索引和阅读不会增加掌握证据。</p>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <section className="card material-upload">
        <h3>上传 PDF</h3>
        <p className="muted">
          上传后自动保存文件记录；默认由后台完成处理并更新章节、知识点和学习计划，无需手动运行任务。
        </p>
        <p>
          当前模型：{provider?.name} · 支持格式：
          {provider?.capabilities.supported_mime_types?.join("、") ||
            "未验证文件支持"}
        </p>
        {!canUpload && (
          <p className="hint">
            请在模型设置中选择原生文件接口并检测 PDF
            能力，当前连接不能上传教材。
          </p>
        )}
        {provider?.capabilities.is_demo && (
          <p className="hint">
            离线演示使用固定操作系统资料，不会理解上传文件内容，不代表真实服务能力。
          </p>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(async (current) => {
              const data = await api(root + "/materials", {
                method: "POST",
                rawBody: file,
                headers: {
                  "Content-Type": "application/pdf",
                  "X-Filename": encodeURIComponent(file.name),
                  "X-File-Consent": "true",
                  "X-Use-Embeddings": String(embeddings),
                  "Idempotency-Key": uploadKey.current,
                },
              });
              if (!current()) return;
              setConsent(false);
              uploadKey.current = key();
              resetEvidence();
              await reload();
              if (current()) setSelected(data);
            });
          }}
        >
          <label>
            选择 PDF（上限 {Math.round((maxBytes || 20971520) / 1048576)} MiB）
            <input
              type="file"
              accept="application/pdf,.pdf"
              required
              disabled={!canUpload || busy}
              onChange={(e) => {
                setFile(e.target.files[0] || null);
                setConsent(false);
                uploadKey.current = key();
              }}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={embeddings}
              disabled={!provider?.capabilities.embedding || busy}
              onChange={(e) => {
                setEmbeddings(e.target.checked);
                uploadKey.current = key();
              }}
            />
            使用已检测的远端 Embedding（摘要与查询也会发送至该服务商）
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              required
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            本次同意将所选文件交给 {provider?.name || "当前服务商"}{" "}
            处理，可能产生费用。原文保存在本机；远端保留遵循该服务商政策。删除会尝试清理，失败时需在服务商控制台核对。
          </label>
          <button
            className="primary"
            disabled={!canUpload || !consent || !file || busy}
          >
            上传并建立索引
          </button>
        </form>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={space.allow_general_knowledge || false}
            disabled={busy}
            onChange={(e) => {
              const allowed = e.target.checked;
              run(async (current) => {
                await api(root, {
                  method: "PATCH",
                  body: { allow_general_knowledge: allowed },
                });
                if (current()) await onRefresh();
              });
            }}
          />
          教材证据不足时，允许通用模型知识补充（内容未核实）
        </label>
      </section>
      <section className="card">
        <h3>资料与处理任务</h3>
        {!rows.length && <p className="muted">尚未上传教材。</p>}
        {rows.map((row) => (
          <article className="material-row" key={row.id}>
            <b>{row.filename}</b>
            <p>
              状态：{row.status} · {row.job?.stage} · {row.job?.progress || 0}%
            </p>
            <progress
              max="100"
              value={row.job?.progress || 0}
              aria-label={row.filename + "处理进度"}
            />
            {(row.warning || row.job?.error_message) && (
              <p className="hint">{row.warning || row.job.error_message}</p>
            )}
            <div className="button-row">
              {row.status !== "deleting" && (
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async (current) => {
                      const result = await api(root + "/materials/" + row.id);
                      if (current()) setSelected(result);
                    })
                  }
                >
                  查看章节与知识点
                </button>
              )}
              {row.job?.status === "failed" && (
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async (current) => {
                      await api("/jobs/" + row.job_id + "/retry", {
                        method: "POST",
                        body: { idempotency_key: key() },
                      });
                      if (current()) await reload();
                    })
                  }
                >
                  重试失败任务
                </button>
              )}
              {["queued", "running"].includes(row.job?.status) &&
                row.job?.kind === "index" && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(async (current) => {
                        await api("/jobs/" + row.job_id + "/cancel", {
                          method: "POST",
                        });
                        if (current()) await reload();
                      })
                    }
                  >
                    取消处理
                  </button>
                )}
              {row.status !== "deleting" && (
                <>
                  <button
                    disabled={busy || !canUpload || !consent}
                    title="请先勾选本次远端处理授权"
                    onClick={() =>
                      run(async (current) => {
                        await api(root + "/materials/" + row.id + "/reindex", {
                          method: "POST",
                          body: {
                            consent: true,
                            use_embeddings: embeddings,
                            idempotency_key: key(),
                          },
                        });
                        if (current()) {
                          setConsent(false);
                          resetEvidence();
                          await reload();
                          await onRefresh();
                        }
                      })
                    }
                  >
                    使用当前模型重新索引
                  </button>
                  <button
                    className="danger"
                    disabled={busy}
                    onClick={() =>
                      run(async (current) => {
                        await api(root + "/materials/" + row.id, {
                          method: "DELETE",
                        });
                        if (current()) {
                          resetEvidence();
                          await reload();
                          await onRefresh();
                        }
                      })
                    }
                  >
                    删除原文与索引
                  </button>
                </>
              )}
            </div>
          </article>
        ))}
      </section>
      {selected && (
        <section className="card">
          <h3>{selected.filename}</h3>
          <p>{selected.retention_notice}</p>
          {(selected.sections || []).map((s) => (
            <article className="material-row" key={s.source_id}>
              <b>{s.heading}</b>
              <p>{s.summary}</p>
              <p>知识点：{s.concepts?.join("、")}</p>
              <small>章节由模型提取，页码未核实</small>
            </article>
          ))}
          <a
            href={"/api/v1" + root + "/materials/" + selected.id + "/download"}
          >
            下载原始 PDF
          </a>
        </section>
      )}
      <section className="card">
        <h3>检索教材</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(async (current) => {
              const result = await api(root + "/materials/search", {
                method: "POST",
                body: { query, mode },
              });
              if (current()) setResults(result);
            });
          }}
        >
          <label>
            问题或关键词
            <input
              required
              maxLength={2000}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label>
            检索方式
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="auto">自动选择可用方式</option>
              <option value="keyword">关键词 + 模型精排（非向量）</option>
              <option
                value="embedding"
                disabled={!provider?.capabilities.embedding}
              >
                远端 Embedding + 模型精排
              </option>
            </select>
          </label>
          <button disabled={busy}>搜索教材证据</button>
        </form>
        {results && (
          <>
            <p>
              实际方式：
              {results.mode === "remote_embedding"
                ? "远端向量 + 模型精排"
                : "关键词 + 模型精排（非向量）"}
            </p>
            {!results.results.length && <p>未找到相关教材证据。</p>}
            <Citations sources={results.results} root={root} />
          </>
        )}
      </section>
    </>
  );
}
