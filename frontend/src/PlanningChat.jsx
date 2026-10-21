import ActionButton from "./ActionButton";
import React, { useState, useRef, useEffect } from "react";
import {
  MessageCircle,
  Send,
  RefreshCw,
  ArrowRight,
  LoaderCircle,
} from "lucide-react";
import { api, key } from "./api";
import { createLatestRequest } from "./latestRequest";
import { createPlanningChatState, shouldSend } from "./planningChatState";

const fieldNames = {
  goal: "学习目标",
  daily_minutes: "每天学习时间",
  target_date: "目标日期",
  expected_level: "学习深度",
  included_concept_ids: "学习范围",
  priority_concept_ids: "优先知识点",
  deferred_concept_ids: "暂缓内容",
  teaching_preferences: "讲解偏好",
  learner_notes: "学习情况",
  stages: "阶段路线",
  added_concepts: "新增知识",
  paused_lesson: "当前课堂",
};
const outcomes = {
  applied: "已生效",
  not_changed: "交流记录",
  clarification_needed: "需要补充信息",
  failed: "未生效",
  conflict: "未生效 · 上下文已变化",
  cancelled: "已取消",
};
const merge = (old, rows) =>
  [...new Map([...old, ...rows].map((r) => [r.id, r])).values()].sort(
    (a, b) =>
      a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
  );
export default function PlanningChat({
  root,
  plan,
  concepts = [],
  onPlanChanged,
  onLessonResumed,
}) {
  const [messages, setMessages] = useState([]),
    [paused, setPaused] = useState([]),
    [draft, setDraft] = useState(""),
    [busy, setBusy] = useState(false),
    [pendingText, setPendingText] = useState(""),
    [error, setError] = useState(""),
    [warning, setWarning] = useState(""),
    [cursor, setCursor] = useState(null),
    [loading, setLoading] = useState(true);
  const reads = useRef(createLatestRequest()),
    actions = useRef(createPlanningChatState(key)),
    bottom = useRef(null),
    resumeGate = useRef(createLatestRequest());
  const current = useRef(messages);
  current.current = messages;
  const hasPending = messages.some((r) => r.status === "processing");
  async function reload(before = null, poll = false) {
    await reads.current.run(
      () =>
        Promise.all([
          api(
            root +
              "/chat/turns" +
              (before ? "?before=" + encodeURIComponent(before) : ""),
          ),
          api(root + "/lessons/paused"),
        ]),
      async ([page, lessons]) => {
        const ended = page.items.some(
          (r) =>
            r.status !== "processing" &&
            current.current.some(
              (o) => o.id === r.id && o.status === "processing",
            ),
        );
        setMessages((old) => merge(old, page.items));
        setPaused(lessons);
        if (!poll) setCursor(page.next_cursor);
        setLoading(false);
        if (ended) {
          try {
            await onPlanChanged();
          } catch (e) {
            setWarning("结果已保存，页面刷新失败：" + e.message);
          }
        }
      },
    );
  }
  useEffect(() => {
    reload().catch((e) => {
      setError(e.message);
      setLoading(false);
    });
    return () => {
      reads.current.invalidate();
      actions.current.invalidate();
      resumeGate.current.invalidate();
    };
  }, [root]);
  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(
      () => reload(null, true).catch((e) => setError(e.message)),
      2000,
    );
    return () => clearInterval(timer);
  }, [root, hasPending]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [messages.length, busy]);
  async function send(content = draft, retry = false, row = null) {
    content = content.trim();
    if (!content || busy) return;
    const submittedDraft = draft;
    if (row) actions.current.recover(row);
    setError("");
    setWarning("");
    setBusy(true);
    setPendingText(content);
    if (!row) setDraft("");
    try {
      await actions.current.runSend(
        content,
        (body) => api(root + "/chat/turns", { method: "POST", body }),
        async (result) => {
          setMessages((old) => merge(old, [result]));
          if (result.status === "completed") {
            try {
              await onPlanChanged();
              await reload(null, true);
            } catch (e) {
              setWarning("修改结果已保存，页面刷新失败：" + e.message);
            }
          }
        },
        retry,
      );
    } catch (e) {
      if (!row) setDraft(submittedDraft);
      setError(e.message);
    } finally {
      setBusy(false);
      setPendingText("");
    }
  }
  const names = new Map(concepts.map((c) => [c.key, c.name]));
  function value(field, value) {
    if (value === null || value === undefined || value === "") return "未设置";
    if (field === "paused_lesson")
      return value === "paused" ? "已暂存，可稍后继续" : "原课堂";
    if (Array.isArray(value)) {
      if (field === "stages")
        return value.map((s) => s.title).join(" → ") || "未设置";
      return value.map((v) => names.get(v) || v).join("、") || "未设置";
    }
    return String(value) + (field === "daily_minutes" ? " 分钟" : "");
  }
  return (
    <>
      <div className="page-title">
        <span className="eyebrow">调整时间 · 明确重点 · 更新计划</span>
        <h1>让计划，跟上你的变化。</h1>
        <p>
          直接告诉学习助手新的时间、重点或想学的内容，明确的需求会自动更新当前空间。
        </p>
      </div>
      <div className="planning-chat-layout">
        <section className="card chat-panel" aria-label="学习对话">
          <div className="section-head">
            <h3>
              <MessageCircle size={18} /> 学习对话
            </h3>
            <ActionButton
              loadingText="正在刷新对话…"
              className="text-button"
              onClick={() => reload().catch((e) => setError(e.message))}
              aria-label="重新读取聊天记录"
            >
              <RefreshCw size={15} />
            </ActionButton>
          </div>
          <div className="chat-transcript" aria-live="polite">
            {cursor && (
              <ActionButton
                loadingText="正在读取历史消息…"
                className="text-button"
                onClick={() => reload(cursor).catch((e) => setError(e.message))}
              >
                加载更早的消息
              </ActionButton>
            )}
            {loading && <p className="muted">正在读取对话…</p>}
            {!loading && !messages.length && (
              <div className="chat-welcome">
                <MessageCircle size={32} />
                <h3>学习需求，随时聊。</h3>
                <p>
                  例如减少每天学习时间、调整重点，或请助手解释计划。聊天会保留，你的作答证据也会继续使用。
                </p>
              </div>
            )}
            {messages.map((row) => (
              <article className="chat-turn" key={row.id}>
                <div className="chat-bubble user-bubble">
                  <small>你</small>
                  <p>{row.content}</p>
                </div>
                <div className="chat-bubble assistant-bubble">
                  <small>
                    学习助手 ·{" "}
                    {new Date(row.created_at).toLocaleString("zh-CN")}
                  </small>
                  {row.reply && <p>{row.reply}</p>}
                  {row.status === "processing" ? (
                    <p className="muted">
                      <LoaderCircle className="spin" size={14} />{" "}
                      正在理解需求、生成安排…
                    </p>
                  ) : (
                    <span
                      className={
                        "chat-outcome " +
                        (row.outcome === "applied" ? "applied" : "")
                      }
                    >
                      {outcomes[row.outcome] || row.status}
                    </span>
                  )}
                  {row.error_message && (
                    <p className="error">{row.error_message}</p>
                  )}
                  {!!row.changes?.length && (
                    <div className="chat-changes">
                      <h4>这次调整了什么</h4>
                      {row.changes.map((change, i) => (
                        <div key={i}>
                          <b>{fieldNames[change.field] || change.field}</b>
                          <p>
                            <span>{value(change.field, change.before)}</span>{" "}
                            <ArrowRight size={13} />{" "}
                            <strong>{value(change.field, change.after)}</strong>
                          </p>
                        </div>
                      ))}
                      {row.plan?.next_action && (
                        <p className="small">
                          下一步：{row.plan.next_action.reason}
                        </p>
                      )}
                    </div>
                  )}
                  {row.retry_allowed && (
                    <ActionButton
                      loadingText="正在重试发送…"
                      disabled={busy}
                      onClick={() => send(row.content, true, row)}
                    >
                      重试这条消息
                    </ActionButton>
                  )}
                </div>
              </article>
            ))}
            {busy && !hasPending && (
              <div className="chat-bubble user-bubble">
                <small>正在发送</small>
                <p>{pendingText}</p>
              </div>
            )}
            <div ref={bottom} />
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
              <ActionButton
                loadingText="正在重试发送…"
                disabled={busy}
                onClick={() => send(draft, true)}
              >
                重试发送
              </ActionButton>
            </div>
          )}
          {warning && (
            <div className="hint" role="status">
              {warning}
            </div>
          )}
          <div className="chat-examples">
            {["每天改成15分钟", "优先复习薄弱知识点", "为什么这样安排"].map(
              (text) => (
                <button
                  key={text}
                  disabled={busy}
                  onClick={() => setDraft(text)}
                >
                  {text}
                </button>
              ),
            )}
          </div>
          <form
            className="chat-composer"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <textarea
              aria-label="发送学习需求"
              placeholder="说说你的新需求，例如：每天 15 分钟，优先复习薄弱知识点…"
              value={draft}
              maxLength={4000}
              disabled={busy}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (shouldSend(e)) {
                  e.preventDefault();
                  if (!hasPending) send();
                }
              }}
            />
            <div>
              <small className="muted">
                Ctrl / ⌘ + Enter 发送 · {draft.length}/4000
              </small>
              <button
                className="primary"
                type="submit"
                disabled={busy || hasPending || !draft.trim()}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Send size={16} />
                )}{" "}
                {busy ? "正在处理" : "发送"}
              </button>
            </div>
          </form>
          <p className="small muted">
            对话使用当前空间的模型，可能产生费用。明确的调整会自动应用，不清楚的需求会先向你确认；掌握情况仍以实际作答为依据。
          </p>
        </section>
        <aside className="chat-plan-summary">
          <section className="card">
            <span className="eyebrow">当前目标与学习安排</span>
            <h3>现在，为你安排</h3>
            <p>{plan?.intent?.goal}</p>
            <p className="small">
              每天 <b>{plan?.daily_minutes}</b> 分钟 ·{" "}
              {plan?.intent?.expected_level}
            </p>
            {plan?.target_date && <p>目标日期：{plan.target_date}</p>}
            {plan?.intent?.teaching_preferences && (
              <p className="hint">
                讲解偏好：{plan.intent.teaching_preferences}
              </p>
            )}
            <p className="small muted">
              调整时间或重点后，学习安排会随之更新。
            </p>
            <hr />
            <h4>下一步与依据</h4>
            <p>{plan?.next_action?.reason}</p>
            {plan?.next_action?.scope_explanations?.map((text) => (
              <p className="small muted" key={text}>
                {text}
              </p>
            ))}
          </section>
          <section className="card">
            <h3>阶段路线</h3>
            {!plan?.stages?.length ? (
              <p className="muted">
                告诉助手想调整的目标或重点，它会结合当前知识结构安排路线。
              </p>
            ) : (
              plan.stages.map((stage, i) => (
                <article className="chat-stage" key={i}>
                  <b>
                    {i + 1}. {stage.title}
                  </b>
                  <p>{stage.objective}</p>
                  <small>
                    {stage.concept_ids
                      .map((id) => names.get(id) || id)
                      .join("、")}{" "}
                    · 建议 {stage.suggested_sessions} 次学习
                  </small>
                </article>
              ))
            )}
          </section>
          {!!paused.length && (
            <section className="card">
              <h3>暂存的课堂</h3>
              <p className="small muted">已读内容与作答保留，可稍后继续。</p>
              {paused.map((lesson) => (
                <article className="chat-stage" key={lesson.id}>
                  <b>{lesson.title}</b>
                  <ActionButton
                    loadingText="正在恢复课堂…"
                    className="text-button"
                    onClick={() =>
                      resumeGate.current
                        .run(
                          () =>
                            api(root + "/lessons/" + lesson.id + "/resume", {
                              method: "POST",
                              body: { idempotency_key: key() },
                            }),
                          onLessonResumed,
                        )
                        .catch((e) => setError(e.message))
                    }
                  >
                    继续原课堂 <ArrowRight size={14} />
                  </ActionButton>
                </article>
              ))}
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
