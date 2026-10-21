import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { createLatestRequest } from "./latestRequest";
import AlgorithmStatus from "./AlgorithmStatus";
import { LoadingNotice } from "./ActionButton";

const labels = { unknown: "待诊断", learning: "学习中", mastered: "已掌握" };
const fraction = (row) =>
  row.rate === null
    ? "暂无足够记录"
    : `${Math.round(row.rate * 100)}%（${row.numerator}/${row.denominator}）`;

export default function LearningReport({ root, embedded = false }) {
  const [days, setDays] = useState(7),
    [data, setData] = useState(null),
    [error, setError] = useState("");
  const reads = useRef(createLatestRequest());
  useEffect(() => {
    setData(null);
    setError("");
    reads.current
      .run(() => api(root + "/report?days=" + days), setData)
      .catch((e) => setError(e.message));
    return () => reads.current.invalidate();
  }, [root, days]);
  return (
    <>
      {!embedded && (
        <div className="page-title">
          <span className="eyebrow">近期作答 · 复习表现 · 掌握变化</span>
          <h1>回看走过的路。</h1>
          <p>从实际作答、回忆和完成记录，看见进步与下一步。</p>
        </div>
      )}
      <label className="report-window">
        统计范围{" "}
        <select
          aria-label="报告统计范围"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={7}>最近 7 天</option>
          <option value={30}>最近 30 天</option>
        </select>
        <LoadingNotice active={!data && !error}>
          正在汇总学习记录…
        </LoadingNotice>
      </label>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!data ? (
        <section className="card" aria-busy={!error}>
          {error
            ? "统计读取未完成，请重新选择统计范围。"
            : "正在整理所选时间范围内的作答与复习记录。"}
        </section>
      ) : (
        <>
          <div className="adaptive-metrics">
            <section className="card">
              <small>实际作答</small>
              <strong>
                {data.evidence.answers}
                <em>次</em>
              </strong>
            </section>
            <section className="card">
              <small>独立作答</small>
              <strong>
                {data.evidence.independent}
                <em>次</em>
              </strong>
            </section>
            <section className="card">
              <small>到期复习</small>
              <strong>
                {data.reviews.due.length}
                <em>项</em>
              </strong>
            </section>
          </div>
          {data.external_imports && (
            <section className="card">
              <h3>导入试卷</h3>
              <p>
                {data.external_imports.diagnostics} 份试卷 ·{" "}
                {data.external_imports.effective_evidence} 条有效外部证据
              </p>
              <p className="small muted">
                按导入时间统计；历史试卷不计为今天在线答题或复习回忆。
              </p>
            </section>
          )}
          <div className="adaptive-columns">
            <section className="card">
              <h3>知识点状态分布</h3>
              <p className="small muted">
                根据已确认的作答记录，查看待诊断、学习中和已掌握的知识点数量。
              </p>
              {Object.entries(data.distribution).map(([status, count]) => (
                <div className="distribution-row" key={status}>
                  <span className={"status " + status}>{labels[status]}</span>
                  <progress
                    max={Math.max(1, data.progress.length)}
                    value={count}
                    aria-label={labels[status] + "知识点数量"}
                  />
                  <b>{count}</b>
                </div>
              ))}
            </section>
            <section className="card">
              <h3>这段时间的表现</h3>
              <p>
                复习后独立回忆：<b>{fraction(data.review_retention)}</b>
              </p>
              <p className="small muted">
                {data.review_retention.denominator}{" "}
                次可靠复习；提示下答对不算独立回忆。
              </p>
              <p>
                任务完成：<b>{fraction(data.task_completion)}</b>
              </p>
              <p className="small muted">
                统计所选时间内开始的课堂；完成讲解阅读并提交全部练习后计为完成。
              </p>
            </section>
          </div>
          <section className="card">
            <h3>状态变化与证据</h3>
            {data.error_concepts.map((row) => (
              <p key={row.concept_id}>
                近期需巩固：{row.name}（{row.count} 次可靠作答错误）
              </p>
            ))}
            {data.progress.map((row) => (
              <article className="review-row" key={row.concept_id}>
                <b>{row.name}</b>
                <span>
                  {labels[row.before]} → {labels[row.after]}{" "}
                  {row.improved && <span className="tag green">有新进展</span>}
                </span>
              </article>
            ))}
            {data.misconceptions.length > 0 && (
              <p>近期误区：{data.misconceptions.join("；")}</p>
            )}
          </section>
          <section className="card next-card">
            <span className="eyebrow">根据学习记录推荐下一步</span>
            <h3>下一步为什么这样安排</h3>
            <p>{data.next_action.reason}</p>
            <p className="small muted">
              结合前置知识、目标重点、作答表现和复习到期时间，推荐当前适合的学习任务。
            </p>
          </section>
          <AlgorithmStatus algorithms={data.algorithms} />
          <p className="small muted">{data.notice}</p>
        </>
      )}
    </>
  );
}
