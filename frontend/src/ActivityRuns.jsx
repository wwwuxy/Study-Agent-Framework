import ActionButton, { LoadingNotice } from "./ActionButton";
import React, { useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { api } from "./api";
import {
  ActivityError,
  activityStatus,
  useActivityResource,
} from "./useActivity";

export default function ActivityRuns({ embedded = false }) {
  const jobs = useActivityResource("/activity-jobs"),
    usage = useActivityResource("/analysis-usage"),
    analyses = useActivityResource("/analyses");
  const [busy, setBusy] = useState("");
  async function retry(row) {
    const current = jobs.actions.checkpoint();
    setBusy(row.id);
    try {
      const r = await jobs.actions.run("retry:" + row.id, (body) =>
        api("/activity-jobs/" + row.id + "/retry", { method: "POST", body }),
      );
      if (r.current) await jobs.reload();
    } catch (e) {
      if (current()) jobs.setError(e.message);
    } finally {
      if (current()) setBusy("");
    }
  }
  return (
    <>
      <div className={embedded ? "section-intro" : "page-title"}>
        {!embedded && (
          <span className="eyebrow">任务状态 · 分析记录 · 每日用量</span>
        )}
        {embedded ? (
          <h2>后台运行与分析用量</h2>
        ) : (
          <h1>后台在做什么，一目了然。</h1>
        )}
        <p>查看学习安排与周报的生成状态，管理 AI 分析记录和每日用量。</p>
      </div>
      <ActivityError message={jobs.error || usage.error || analyses.error} />
      <LoadingNotice active={usage.loading && !usage.data}>
        正在读取 AI 分析用量…
      </LoadingNotice>
      {usage.data && (
        <section className="card activity-usage">
          <div className="section-head">
            <h3>AI 分析每日用量</h3>
            <span className="tag">UTC {usage.data.utc_date}</span>
          </div>
          <div className="activity-metrics">
            <div>
              <small>已发起分析</small>
              <strong>
                {usage.data.calls}
                <em>/ {usage.data.call_limit}</em>
              </strong>
            </div>
            <div>
              <small>已用及预留 Token</small>
              <strong>
                {usage.data.occupied_tokens.toLocaleString()}
                <em>/ {usage.data.token_limit.toLocaleString()}</em>
              </strong>
            </div>
            <div>
              <small>已确认 Token</small>
              <strong>{usage.data.actual_tokens.toLocaleString()}</strong>
            </div>
            <div>
              <small>用量未知／处理中</small>
              <strong>
                {usage.data.unknown_calls}
                <em>次</em>
              </strong>
            </div>
          </div>
          <p className="small muted">{usage.data.notice}</p>
          <p className="small muted">实际费用请以模型服务商账单为准。</p>
        </section>
      )}
      <section className="card activity-runs">
        <h3>手动 AI 分析记录</h3>
        <LoadingNotice active={analyses.loading && !analyses.data}>
          正在读取分析记录…
        </LoadingNotice>
        {analyses.data && !analyses.data.items.length && (
          <p className="muted">
            暂无分析记录。可在「今日任务」或历史周报中生成 AI
            分析，获取学习建议。
          </p>
        )}
        {analyses.data?.items.map((row) => (
          <article key={row.id}>
            <div className="section-head">
              <h4>
                {row.source_kind === "daily_plan" ? "每日计划" : "自然周报"}分析
              </h4>
              <span className="tag">
                {activityStatus[row.status] || row.status}
              </span>
            </div>
            <p className="small muted">
              {new Date(row.created_at).toLocaleString("zh-CN")} · 空间{" "}
              {row.study_space_id}
            </p>
            <p className="small muted">
              已预留 {row.reserved_tokens} Token ·{" "}
              {row.actual_tokens === null
                ? "实际用量未知／处理中"
                : `实际 ${row.actual_tokens} Token`}
            </p>
            {row.error_message && <p className="hint">{row.error_message}</p>}
            {row.content && <p>{row.content.summary}</p>}
          </article>
        ))}
        {analyses.data?.next_cursor && (
          <ActionButton loadingText="正在读取分析记录…" onClick={analyses.more}>
            加载更早分析
          </ActionButton>
        )}
      </section>
      <section className="card activity-runs">
        <div className="section-head">
          <h3>
            <Activity size={18} /> 周期任务记录
          </h3>
          <ActionButton
            loadingText="正在刷新…"
            onClick={() =>
              Promise.all([
                jobs.reload(),
                usage.reload(),
                analyses.reload(),
              ]).catch(() => {})
            }
          >
            <RefreshCw size={15} /> 刷新
          </ActionButton>
        </div>
        <p className="small muted">
          系统自动整理今日任务、复习提醒和自然周报；整理过程使用已有记录，不调用模型。
        </p>
        {jobs.loading && !jobs.data && <p>正在读取运行记录…</p>}
        {jobs.data && !jobs.data.items.length && (
          <p className="muted">
            暂无运行记录。系统整理学习安排或生成周报后，会在这里显示处理结果。
          </p>
        )}
        {jobs.data?.items.map((row) => (
          <article key={row.id}>
            <div className="section-head">
              <h4>
                {row.kind === "daily_coordinate"
                  ? "每日学习协调"
                  : "自然周统计"}
              </h4>
              <span className="status unknown">
                {activityStatus[row.status]}
              </span>
            </div>
            <p className="small muted">
              本轮尝试 {row.attempts}/3 · 累计运行 {row.executions} 次 ·
              计划运行时间 {new Date(row.available_at).toLocaleString("zh-CN")}
            </p>
            {row.error_message && (
              <p className="hint">
                {row.error_message} · {row.error_code}
              </p>
            )}
            {row.status === "dead_letter" && (
              <ActionButton
                loadingText="正在重试后台任务…"
                disabled={!!busy}
                onClick={() => retry(row)}
              >
                重试后台任务
              </ActionButton>
            )}
          </article>
        ))}
        {jobs.data?.next_cursor && (
          <ActionButton loadingText="正在读取历史记录…" onClick={jobs.more}>
            加载更早记录
          </ActionButton>
        )}
      </section>
    </>
  );
}
