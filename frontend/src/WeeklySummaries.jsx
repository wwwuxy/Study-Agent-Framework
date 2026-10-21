import ActionButton, { LoadingNotice } from "./ActionButton";
import React, { useState } from "react";
import { ArrowUpRight, BarChart3, CalendarDays, RefreshCw } from "lucide-react";
import { api } from "./api";
import { ActivityError, useActivityResource } from "./useActivity";
import AIAnalysis from "./AIAnalysis";

const fraction = (row) =>
  row.rate === null
    ? "暂无可靠记录"
    : `${Math.round(row.rate * 100)}% · ${row.numerator}/${row.denominator}`;
export default function WeeklySummaries({ root, onRolling, embedded = false }) {
  const [selected, setSelected] = useState("current"),
    [busy, setBusy] = useState(false);
  const list = useActivityResource(root + "/weekly-summaries");
  const report = useActivityResource(root + "/weekly-summaries/" + selected);
  const data = report.data;
  async function refresh() {
    const current = list.actions.checkpoint();
    setBusy(true);
    try {
      const r = await list.actions.run("refresh-week", (body) =>
        api(root + "/weekly-summaries/refresh", { method: "POST", body }),
      );
      if (r.current) {
        await list.reload();
        setSelected(r.value.id);
      }
    } catch (e) {
      if (current()) list.setError(e.message);
    } finally {
      if (current()) setBusy(false);
    }
  }
  return (
    <>
      {!embedded && (
        <div className="page-title">
          <span className="eyebrow">每周作答 · 掌握变化 · 目标进展</span>
          <h1>回看这一周，找到下一步。</h1>
          <p>汇总一周作答、复习与掌握变化，找到值得继续巩固的知识。</p>
        </div>
      )}
      <div className="activity-report-tools">
        <label className="weekly-period-field">
          <span className="weekly-period-label">自然周</span>
          <select
            aria-label="选择学习周报"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="current">本周 · 即时预览</option>
            {list.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.week_start} 起的一周
              </option>
            ))}
          </select>
          <LoadingNotice active={report.loading}>
            正在读取所选周报…
          </LoadingNotice>
        </label>
        <ActionButton
          loadingText="正在读取上周周报…"
          className="weekly-summary-refresh"
          disabled={busy}
          aria-busy={busy}
          onClick={refresh}
        >
          <RefreshCw
            size={15}
            className={busy ? "spin" : undefined}
            aria-hidden="true"
          />
          {busy ? "正在读取…" : "查看上周周报"}
        </ActionButton>
        {!embedded && (
          <button className="text-button" onClick={onRolling}>
            查看近 7／30 天统计
            <ArrowUpRight size={14} />
          </button>
        )}
      </div>
      <ActivityError message={list.error || report.error} />
      {!data && <section className="card">正在读取周报…</section>}
      {data && (
        <>
          <section className="activity-week-banner">
            <div>
              <span>
                <CalendarDays size={15} /> {data.week_start} · {data.timezone}
              </span>
              <h2>
                {data.preview ? "这一周，正在积累。" : "每一份进步，都有记录。"}
              </h2>
              <p>
                {data.preview
                  ? "当前自然周的即时统计"
                  : "已结束自然周的学习总结"}{" "}
                · {data.answers}次作答 · {data.evidence_count}条有效证据
              </p>
            </div>
            <BarChart3 size={52} />
          </section>
          <div className="activity-metrics">
            {[
              ["独立作答", data.independent, "次"],
              ["辅助作答", data.assisted, "次"],
              [
                "已掌握变化",
                `${data.before_mastered} → ${data.after_mastered}`,
                "个",
              ],
              ["待核实作答", data.uncertain, "次"],
            ].map(([name, value, unit]) => (
              <section className="card" key={name}>
                <small>{name}</small>
                <strong>
                  {value}
                  <em>{unit}</em>
                </strong>
              </section>
            ))}
          </div>
          <div className="activity-columns">
            <section className="card">
              <h3>这一周的学习节奏</h3>
              <div className="activity-stat-line">
                <span>任务完成</span>
                <b>{fraction(data.task_completion)}</b>
              </div>
              <div className="activity-stat-line">
                <span>复习后独立回忆</span>
                <b>{fraction(data.review_retention)}</b>
              </div>
              <div className="activity-stat-line">
                <span>当前到期复习</span>
                <b>{data.due_reviews}项</b>
              </div>
              <div className="activity-stat-line">
                <span>跳过任务</span>
                <b>{data.skipped_tasks}项</b>
              </div>
              <h4>值得再巩固的知识</h4>
              <p>
                {data.error_concepts.join("、") ||
                  "这一周暂无可确认的错题记录。"}
              </p>
            </section>
            <section className="card activity-forecast">
              <span className="eyebrow">结合近期进展评估目标</span>
              <h3>离当前目标，还有多远？</h3>
              <strong>
                {data.forecast.status === "achieved"
                  ? "当前范围已初步达标"
                  : data.forecast.earliest
                    ? `${data.forecast.earliest} — ${data.forecast.latest}`
                    : "暂不能可靠预测"}
              </strong>
              <p>{data.forecast.reason}</p>
              <p className="small muted">
                剩余{data.forecast.remaining_concepts}个知识点 ·{" "}
                {data.forecast.sample_weeks}个完整周记录 · 各周掌握净增：
                {data.forecast.weekly_gains.join("、") || "暂无"}
              </p>
              <p className="small muted">
                目标日期：{data.forecast.target_date || "未设置"}
              </p>
              <p className="small muted">{data.forecast.uncertainty}</p>
            </section>
          </div>
          <p className="small muted">{data.notice}</p>
          {!data.preview ? (
            <AIAnalysis
              key={root + data.id}
              root={root}
              sourceKind="weekly_summary"
              sourceId={data.id}
            />
          ) : (
            <p className="hint">
              本周数据持续更新。选择已保存的历史周报后，可生成 AI
              分析，获取复盘建议。
            </p>
          )}
        </>
      )}
      {list.data?.next_cursor && (
        <ActionButton loadingText="正在读取历史周报…" onClick={list.more}>
          加载更早周报
        </ActionButton>
      )}
    </>
  );
}
