import ActionButton from "./ActionButton";
import React, { useEffect, useRef, useState } from "react";
import { FileText, LoaderCircle, RefreshCw, Trash2 } from "lucide-react";
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
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [consent, setConsent] = useState(false),
    [pendingDelete, setPendingDelete] = useState(null),
    [loading, setLoading] = useState(true);
  const actions = useRef(createExamDiagnosticState({ api, makeKey: key })),
    reads = useRef(createLatestRequest()),
    alive = useRef(true),
    notified = useRef(new Set()),
    cancelDeleteButton = useRef(null);
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
    if (pendingDelete) cancelDeleteButton.current?.focus();
  }, [pendingDelete]);
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
    setBusy("upload");
    setError("");
    try {
      await actions.current.upload(root, files, metadata, allow, accept);
    } finally {
      if (alive.current) setBusy("");
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
    setBusy(action);
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
      if (alive.current) setBusy("");
    }
  }
  async function patch(questionId, changes) {
    setBusy("patch");
    try {
      await actions.current.patch(
        root,
        selected.id,
        questionId,
        changes,
        accept,
      );
    } finally {
      if (alive.current) setBusy("");
    }
  }
  async function remove() {
    const target = pendingDelete;
    setBusy("delete");
    setError("");
    reads.current.invalidate();
    try {
      await actions.current.remove(root, target, async () => {
        if (!alive.current) return;
        setRows((old) => old.filter((row) => row.id !== target.id));
        setSelected((old) => (old?.id === target.id ? null : old));
        setPendingDelete(null);
        setConsent(false);
        try {
          await history();
          if (target.status === "completed") await onStateChanged();
        } catch (err) {
          if (alive.current)
            setError("诊断已删除，但页面刷新失败：" + err.message);
        }
      });
    } catch (err) {
      if (alive.current) setError(err.message);
    } finally {
      if (alive.current) setBusy("");
    }
  }
  return (
    <>
      <div className="page-title">
        <span className="eyebrow">逐题诊断 · 发现薄弱 · 定向巩固</span>
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
            busy={!!busy}
            uploading={busy === "upload"}
          />
          <section className="card">
            <div className="exam-question-heading">
              <h3>诊断历史</h3>
              <ActionButton
                loadingText="正在刷新诊断历史…"
                className="icon-button"
                type="button"
                aria-label="刷新诊断历史"
                onClick={() => history().catch((e) => setError(e.message))}
              >
                <RefreshCw size={16} />
              </ActionButton>
            </div>
            {loading ? (
              <p className="muted">读取历史记录…</p>
            ) : !rows.length ? (
              <p className="muted">上传第一份已批改试卷，开始诊断。</p>
            ) : (
              <div className="exam-history">
                {rows.map((row) => (
                  <div className="exam-history-item" key={row.id}>
                    <ActionButton
                      loadingText="正在读取诊断报告…"
                      className={
                        "exam-history-select " +
                        (selected?.id === row.id ? "active" : "")
                      }
                      disabled={busy}
                      onClick={() => select(row)}
                    >
                      <span>{row.name}</span>
                      <small>
                        {statuses[row.status] || row.status} ·{" "}
                        {new Date(row.created_at).toLocaleDateString()}
                      </small>
                    </ActionButton>
                    <button
                      className="icon-button exam-history-delete"
                      type="button"
                      aria-label={"删除诊断：" + row.name}
                      title="删除诊断"
                      disabled={busy}
                      onClick={() => {
                        setError("");
                        setPendingDelete(row);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {cursor && (
              <ActionButton
                loadingText="正在读取历史记录…"
                disabled={busy}
                onClick={() =>
                  history(cursor).catch((e) => setError(e.message))
                }
              >
                加载更早记录
              </ActionButton>
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
                  <ActionButton
                    loadingText="正在重试清理…"
                    disabled={busy}
                    onClick={() => mutate("retry")}
                  >
                    重试远端清理
                  </ActionButton>
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
                  <ActionButton
                    loadingText="正在取消诊断…"
                    disabled={busy}
                    onClick={() => mutate("cancel")}
                  >
                    取消本次处理
                  </ActionButton>
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
                      <ActionButton
                        loadingText="正在提交诊断任务…"
                        className="primary"
                        disabled={busy || !consent}
                        onClick={() =>
                          mutate(
                            selected.status === "draft" ? "start" : "retry",
                          )
                        }
                      >
                        {selected.status === "draft" ? "开始诊断" : "重试处理"}
                      </ActionButton>
                    </>
                  )}
                  {selected.status === "draft" && (
                    <ActionButton
                      loadingText="正在丢弃草稿…"
                      disabled={busy}
                      onClick={() => mutate("draft", "DELETE")}
                    >
                      丢弃草稿
                    </ActionButton>
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
      {pendingDelete && (
        <div
          className="modal-backdrop"
          onClick={() => {
            if (!busy) setPendingDelete(null);
          }}
        >
          <div
            className="modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-exam-title"
            aria-describedby="delete-exam-description"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape" && !busy) setPendingDelete(null);
            }}
          >
            <h2 id="delete-exam-title">删除这份诊断？</h2>
            <p>{pendingDelete.name}</p>
            <p id="delete-exam-description" className="muted">
              报告和本地试卷附件将删除，无法恢复。正在处理的任务将停止后续处理，远端文件将进入清理队列。
              已完成诊断导入的学习证据会撤回，并重新计算知识状态与学习计划。
            </p>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <div className="button-row">
              <button
                ref={cancelDeleteButton}
                disabled={busy}
                onClick={() => setPendingDelete(null)}
              >
                保留诊断
              </button>
              <ActionButton
                loadingText="正在删除诊断…"
                className="danger"
                disabled={busy}
                onClick={remove}
              >
                {busy ? "正在删除…" : "确认删除"}
              </ActionButton>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
