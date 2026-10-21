import ActionButton from "./ActionButton";
import React, { useEffect, useRef, useState } from "react";
import { ArrowRight, History } from "lucide-react";
import { api, key } from "./api";
import { createLatestRequest } from "./latestRequest";
import { createScopedAction } from "./scopedAction";

const phases = { Learning: "学习中", Review: "复习中", Relearning: "重新巩固" };
const when = (value) =>
  new Date(value).toLocaleString("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  });

export default function Reviews({
  root,
  onStarted,
  dueOnly = false,
  onViewAll,
  embedded = false,
}) {
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const reads = useRef(createLatestRequest()),
    actions = useRef(createScopedAction());
  const requests = useRef(new Map());
  async function reload() {
    await reads.current.run(() => api(root + "/reviews"), setData);
  }
  useEffect(() => {
    reload().catch((e) => setError(e.message));
    const timer = setInterval(
      () => reload().catch((e) => setError(e.message)),
      15000,
    );
    return () => {
      clearInterval(timer);
      reads.current.invalidate();
      actions.current.invalidate();
    };
  }, [root]);
  async function start(concept) {
    setBusy(true);
    setError("");
    if (!requests.current.has(concept)) requests.current.set(concept, key());
    try {
      await actions.current.run(
        () =>
          api(root + "/reviews/start", {
            method: "POST",
            body: {
              concept_id: concept,
              idempotency_key: requests.current.get(concept),
            },
          }),
        onStarted,
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (dueOnly)
    return (
      <section className="card today-reviews" aria-label="复习到期">
        <div className="section-head">
          <h3>
            <History size={18} /> 复习到期
          </h3>
          {data && <span className="tag">{data.due.length} 个知识点</span>}
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {!data && !error && <p className="muted">正在读取到期复习…</p>}
        {data && !data.due.length && (
          <p className="muted">当前没有到期复习，可以按今天的安排继续学习。</p>
        )}
        {data?.due.map((row) => (
          <article className="review-row" key={row.id}>
            <div>
              <b>{row.name}</b>
              <p className="small muted">
                {phases[row.state] || row.state} · {when(row.due)}
              </p>
            </div>
            <ActionButton
              loadingText="正在准备复习…"
              className="primary"
              disabled={busy}
              onClick={() => start(row.concept_id)}
            >
              开始 / 继续复习
              <ArrowRight size={14} />
            </ActionButton>
          </article>
        ))}
        {onViewAll && (
          <button className="text-button" onClick={onViewAll}>
            查看全部复习安排 <ArrowRight size={14} />
          </button>
        )}
      </section>
    );
  return (
    <>
      <div className={embedded ? "section-intro" : "page-title"}>
        {!embedded && <span className="eyebrow">按回忆表现安排下次复习</span>}
        {embedded ? (
          <h2>在合适的时间，再想一次。</h2>
        ) : (
          <h1>在合适的时间，再想一次。</h1>
        )}
        <p>根据每次回忆表现安排下次复习，优先巩固已到期的知识点。</p>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!data ? (
        <section className="card">正在读取复习安排…</section>
      ) : (
        <>
          <div className="adaptive-metrics">
            <section className="card">
              <small>现在可以复习</small>
              <strong>{data.due.length}</strong>
            </section>
            <section className="card">
              <small>尚未到期</small>
              <strong>{data.upcoming.length}</strong>
            </section>
            <section className="card">
              <small>待建立作答证据</small>
              <strong>{data.unassessed.length}</strong>
            </section>
          </div>
          {[
            ["due", "现在，温故知新"],
            ["upcoming", "接下来的复习"],
            ["unassessed", "先学习，再建立记忆"],
          ].map(([group, title]) => (
            <section className="card review-group" key={group}>
              <div className="section-head">
                <h3>{title}</h3>
                <span className="muted small">
                  {data[group].length} 个知识点
                </span>
              </div>
              {!data[group].length && (
                <p className="muted">
                  {group === "due"
                    ? "当前没有到期复习，可以继续学习。"
                    : "暂无安排。"}
                </p>
              )}
              {data[group].map((row) => (
                <article className="review-row" key={row.id}>
                  <div>
                    <b>{row.name}</b>
                    <p className="small muted">
                      {group === "unassessed"
                        ? "尚无足够作答记录，先完成诊断或练习以建立复习安排。"
                        : `${phases[row.state] || row.state} · ${when(row.due)}`}
                    </p>
                  </div>
                  {group === "due" && (
                    <ActionButton
                      loadingText="正在准备复习…"
                      className="primary"
                      disabled={busy}
                      onClick={() => start(row.concept_id)}
                    >
                      开始 / 继续复习
                    </ActionButton>
                  )}
                </article>
              ))}
            </section>
          ))}
          <p className="small muted">
            复习提醒用于安排巩固时间，不等同于掌握评定。当前估计基于默认参数，请结合实际回忆情况判断。
          </p>
        </>
      )}
    </>
  );
}
