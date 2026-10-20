import React, { useEffect, useRef, useState } from "react";
import { FileText, LoaderCircle, RefreshCw } from "lucide-react";
import { api, key } from "./api";
import { createLatestRequest } from "./latestRequest";
import { createExamDiagnosticState } from "./examDiagnosticState";
import ExamUpload from "./ExamUpload";
import ExamReport from "./ExamReport";

const statuses = {
  draft: "待上传完整",
  queued: "排队中",
  running: "处理中",
  completed: "诊断完成",
  failed: "处理失败",
  cancelled: "已取消",
};
const stages = {
  queued: "正在识别试卷",
  analyzing: "正在生成诊断",
  publishing: "正在更新学习状态",
  completed: "已完成",
};

export default function ExamDiagnostics({
  root,
  concepts = [],
  onStateChanged,
}) {
  const [capabilities, setCapabilities] = useState(null),
    [rows, setRows] = useState([]),
    [selected, setSelected] = useState(null),
    [cursor, setCursor] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [consent, setConsent] = useState(false),
    [loading, setLoading] = useState(true);
  const actions = useRef(createExamDiagnosticState({ api, makeKey: key })),
    reads = useRef(createLatestRequest()),
    alive = useRef(true),
    notified = useRef(new Set());
  const base = root + "/exam-diagnostics";
  async function history(before = null) {
    await reads.current.run(
      () => api(base + (before ? "?before=" + encodeURIComponent(before) : "")),
      (page) => {
        setRows((old) =>
          before
            ? [
                ...new Map(
                  [...old, ...page.items].map((r) => [r.id, r]),
                ).values(),
              ]
            : page.items,
        );
        setCursor(page.next_cursor);
        setLoading(false);
      },
    );
  }
  async function accept(value) {
    if (!alive.current) return;
    setSelected(value);
    if (value?.status === "completed") {
      const identity = value.id + ":" + value.version;
      if (!notified.current.has(identity)) {
        notified.current.add(identity);
        try {
          await onStateChanged();
        } catch (err) {
          if (alive.current)
            setError("诊断已保存，学习概览刷新失败：" + err.message);
        }
      }
    }
    if (alive.current) await history();
  }
  useEffect(() => {
    alive.current = true;
    Promise.all([
      api(base + "/capabilities").then((value) => {
        if (alive.current) setCapabilities(value);
      }),
      history(),
    ]).catch((err) => {
      if (alive.current) {
        setError(err.message);
        setLoading(false);
      }
    });
    return () => {
      alive.current = false;
      reads.current.invalidate();
      actions.current.invalidate();
    };
  }, [root]);
  const pending = selected && ["queued", "running"].includes(selected.status);
  useEffect(() => {
    if (!pending) return;
    let stopped = false;
    const timer = setInterval(
      () =>
        actions.current
          .poll(root, selected.id, (value) => {
            if (!stopped) return accept(value);
          })
          .catch((err) => {
            if (!stopped && alive.current) setError(err.message);
          }),
      2000,
    );
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [root, selected?.id, pending]);
  async function upload(files, metadata, allow) {
    setBusy(true);
    setError("");
    try {
      await actions.current.upload(root, files, metadata, allow, accept);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function select(row) {
    setError("");
    setConsent(false);
    try {
      await actions.current.poll(root, row.id, accept);
    } catch (err) {
      if (alive.current) setError(err.message);
    }
  }
  async function mutate(action, method = "POST") {
    setBusy(true);
    setError("");
    try {
      await actions.current.action(
        root,
        selected,
        action,
        consent,
        async (value) => {
          if (!alive.current) return;
          setConsent(false);
          if (value) await accept(value);
          else {
            setSelected(null);
            await history();
          }
        },
        method,
      );
    } catch (err) {
      if (alive.current) setError(err.message);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function patch(questionId, changes) {
    setBusy(true);
    try {
      await actions.current.patch(
        root,
        selected.id,
        questionId,
        changes,
        accept,
      );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <>
      <div className="page-title">
        <span className="eyebrow">LEARN FROM EVERY EXAM</span>
        <h1>成绩诊断</h1>
        <p>上传老师批改好的试卷，看清知识薄弱处，让下一步学习有据可依。</p>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="exam-layout">
        <aside className="exam-controls">
          <ExamUpload
            capabilities={capabilities}
            onUpload={upload}
            busy={busy}
          />
          <section className="card">
            <div className="exam-question-heading">
              <h3>诊断历史</h3>
              <button
                className="icon-button"
                type="button"
                aria-label="刷新诊断历史"
                onClick={() => history().catch((e) => setError(e.message))}
              >
                <RefreshCw size={16} />
              </button>
            </div>
            {loading ? (
              <p className="muted">读取历史记录…</p>
            ) : !rows.length ? (
              <p className="muted">上传第一份已批改试卷，开始诊断。</p>
            ) : (
              <div className="exam-history">
                {rows.map((row) => (
                  <button
                    key={row.id}
                    className={selected?.id === row.id ? "active" : ""}
                    onClick={() => select(row)}
                  >
                    <span>{row.name}</span>
                    <small>
                      {statuses[row.status] || row.status} ·{" "}
                      {new Date(row.created_at).toLocaleDateString()}
                    </small>
                  </button>
                ))}
              </div>
            )}
            {cursor && (
              <button
                disabled={busy}
                onClick={() =>
                  history(cursor).catch((e) => setError(e.message))
                }
              >
                加载更早记录
              </button>
            )}
          </section>
        </aside>
        <div className="exam-content">
          {!selected ? (
            <section className="card exam-empty">
              <FileText size={46} />
              <h2>从一份试卷，看见下一步</h2>
              <p>选择左侧历史记录，或上传新的已批改试卷。</p>
              <p className="small muted">
                报告包含逐题结果、老师批改依据、知识点表现及学习状态变化。
              </p>
            </section>
          ) : selected.status === "completed" ? (
            <>
              <ExamReport
                key={selected.id}
                root={root}
                diagnostic={selected}
                concepts={concepts}
                onUpdated={patch}
                busy={busy}
              />
              {selected.cleanup_warning && (
                <div className="card">
                  <p className="hint">{selected.cleanup_warning}</p>
                  <button disabled={busy} onClick={() => mutate("retry")}>
                    重试远端清理
                  </button>
                </div>
              )}
            </>
          ) : (
            <section className="card exam-task" aria-live="polite">
              <span className="eyebrow">{statuses[selected.status]}</span>
              <h2>{selected.name}</h2>
              {pending ? (
                <>
                  <LoaderCircle className="spin" size={32} />
                  <h3>
                    {selected.status === "queued"
                      ? "等待后台处理"
                      : stages[selected.task?.stage] || "正在识别试卷"}
                  </h3>
                  <p className="muted">
                    任务已保存，可以离开页面后再回来查看。清晰的批改结果会在报告发布时更新学习状态。
                  </p>
                  <button disabled={busy} onClick={() => mutate("cancel")}>
                    取消本次处理
                  </button>
                </>
              ) : (
                <>
                  {selected.task?.error_message && (
                    <p className="error" role="alert">
                      {selected.task.error_message}
                    </p>
                  )}
                  {selected.status === "draft" && (
                    <p className="muted">
                      {selected.attachments.every((a) => a.received)
                        ? "文件已上传，授权后即可开始识别。"
                        : "附件尚未上传完整，可丢弃草稿后重新选择文件。"}
                    </p>
                  )}
                  {(selected.status !== "draft" ||
                    selected.attachments.every((a) => a.received)) && (
                    <>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={consent}
                          onChange={(e) => setConsent(e.target.checked)}
                        />
                        同意本次由当前用户模型处理试卷，知悉费用及远端保留政策。
                      </label>
                      <button
                        className="primary"
                        disabled={busy || !consent}
                        onClick={() =>
                          mutate(
                            selected.status === "draft" ? "start" : "retry",
                          )
                        }
                      >
                        {selected.status === "draft" ? "开始诊断" : "重试处理"}
                      </button>
                    </>
                  )}
                  {selected.status === "draft" && (
                    <button
                      disabled={busy}
                      onClick={() => mutate("draft", "DELETE")}
                    >
                      丢弃草稿
                    </button>
                  )}
                  <p className="small muted">
                    尚未发布成功报告时，不会增加有效学习证据。
                  </p>
                </>
              )}
            </section>
          )}
        </div>
      </div>
    </>
  );
}
