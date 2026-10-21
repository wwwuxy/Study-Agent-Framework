import ActionButton from "./ActionButton";
import React, { useState } from "react";
import {
  ArrowRight,
  CalendarDays,
  Check,
  Clock,
  RefreshCw,
  Target,
} from "lucide-react";
import { api } from "./api";
import {
  ActivityError,
  activityStatus,
  useActivityResource,
} from "./useActivity";
import AIAnalysis from "./AIAnalysis";
import Reviews from "./Reviews";

const actionNames = {
  DIAGNOSE: "初始诊断",
  LEARN_CONCEPT: "学习新知",
  REMEDIATE: "修复误区",
  PRACTICE: "定向练习",
  ASSESS: "阶段测评",
  REVIEW: "间隔复习",
};
export default function DailyTasks({
  root,
  onStarted,
  onReviewStarted,
  onViewReviews,
}) {
  const resource = useActivityResource(root + "/daily-plans/today");
  const suggestions = useActivityResource(root + "/suggestions");
  const [busy, setBusy] = useState("");
  const plan = resource.data?.plan;
  async function mutate(name, path, after) {
    const current = resource.actions.checkpoint();
    setBusy(name);
    resource.setError("");
    let saved = false;
    try {
      const outcome = await resource.actions.run(name, (body) =>
        api(root + path, { method: "POST", body }),
      );
      saved = true;
      if (!outcome.current) return;
      if (after) {
        await after(outcome.value);
        return;
      }
      await resource.reload();
      await suggestions.reload();
    } catch (e) {
      if (current())
        resource.setError(
          (saved ? "操作已保存，刷新未完成：" : "") + e.message,
        );
    } finally {
      if (current()) setBusy("");
    }
  }
  const completed =
    plan?.slots.filter((s) => s.task.status === "completed").length || 0;
  return (
    <>
      <div className="page-title">
        <span className="eyebrow">每日时间 · 优先任务 · 到期复习</span>
        <h1>把今天，安排得刚刚好。</h1>
        <p>结合学习目标、每日可用时间和到期复习，安排今天优先完成的任务。</p>
      </div>
      <ActivityError message={resource.error} />
      <section className="activity-day-hero">
        <div>
          <span className="activity-date">
            <CalendarDays size={15} />
            {plan?.local_date || "今日学习"}
            {plan && ` · ${plan.timezone}`}
          </span>
          <h2>
            {plan
              ? `今天，专注 ${plan.budget_minutes} 分钟。`
              : "为今天留一点学习时间。"}
          </h2>
          <p>
            {plan
              ? `${plan.slots.length}项安排 · ${completed}项已完成 · ${plan.backlog.length}项待安排`
              : "后台会根据当前目标整理安排，也可以立即生成。"}
          </p>
        </div>
        <ActionButton
          loadingText="正在更新今日安排…"
          disabled={!!busy}
          onClick={() => mutate("refresh", "/daily-plans/refresh")}
        >
          <RefreshCw size={16} /> {plan ? "更新今日安排" : "生成今日安排"}
        </ActionButton>
      </section>
      {plan?.warning && <p className="hint">{plan.warning}</p>}
      <div className="activity-columns">
        <div className="activity-stack">
          {resource.loading && !plan && (
            <section className="card">正在读取今日安排…</section>
          )}
          {!resource.loading && !plan && (
            <section className="card">
              <h3>今日安排</h3>
              <p className="muted">
                尚未生成今日安排。点击上方按钮开始规划，也可以先完成到期复习。
              </p>
            </section>
          )}
          {plan && (
            <>
              <section className="card activity-tasks">
                <div className="section-head">
                  <h3>
                    <Target size={18} /> 今天的优先事项
                  </h3>
                  <span className="small muted">按学习计划安排</span>
                </div>
                {!plan.slots.length && (
                  <p className="muted">
                    当前没有新的可执行安排，可更新计划或继续「学习概要 →
                    学习概览」中的任务。
                  </p>
                )}
                {plan.slots.map(
                  ({ task, allocated_minutes, carried_over }, i) => (
                    <article className="activity-task" key={task.id}>
                      <span
                        className={
                          "activity-task-number " +
                          (task.status === "completed" ? "done" : "")
                        }
                      >
                        {task.status === "completed" ? (
                          <Check size={17} />
                        ) : (
                          String(i + 1).padStart(2, "0")
                        )}
                      </span>
                      <div className="activity-task-body">
                        <div className="section-head">
                          <h3>{task.name}</h3>
                          <span
                            className={
                              "status " +
                              (task.status === "completed"
                                ? "mastered"
                                : "learning")
                            }
                          >
                            {activityStatus[task.status]}
                          </span>
                        </div>
                        <p className="small muted">
                          {actionNames[task.action] || task.action} ·{" "}
                          <Clock size={11} /> {allocated_minutes}分钟{" "}
                          {carried_over && "· 继续之前的任务"}
                        </p>
                        <p>{task.reason}</p>
                        {["pending", "in_progress"].includes(task.status) && (
                          <div className="button-row">
                            <ActionButton
                              loadingText="正在准备学习任务…"
                              className="primary"
                              disabled={!!busy}
                              onClick={() =>
                                mutate(
                                  "start:" + task.id,
                                  `/tasks/${task.id}/start`,
                                  onStarted,
                                )
                              }
                            >
                              {task.status === "in_progress"
                                ? "继续任务"
                                : "开始这一步"}
                              <ArrowRight size={14} />
                            </ActionButton>
                            <ActionButton
                              loadingText="正在核对完成情况…"
                              disabled={!!busy}
                              onClick={() =>
                                mutate(
                                  "complete:" + task.id,
                                  `/tasks/${task.id}/complete`,
                                )
                              }
                            >
                              核对完成
                            </ActionButton>
                            <ActionButton
                              loadingText="正在保存…"
                              className="text-button"
                              disabled={!!busy}
                              onClick={() =>
                                mutate(
                                  "skip:" + task.id,
                                  `/tasks/${task.id}/skip`,
                                )
                              }
                            >
                              跳过
                            </ActionButton>
                            <ActionButton
                              loadingText="正在调整日期…"
                              className="text-button"
                              disabled={!!busy}
                              onClick={() =>
                                mutate(
                                  "postpone:" + task.id,
                                  `/tasks/${task.id}/postpone`,
                                )
                              }
                            >
                              改到明天
                            </ActionButton>
                          </div>
                        )}
                      </div>
                    </article>
                  ),
                )}
              </section>
              {!!plan.backlog.length && (
                <section className="card">
                  <h3>留待安排</h3>
                  <p className="small muted">
                    暂未排入今日的任务会保留在这里，后续结合前置知识和可用时间安排。
                  </p>
                  {plan.backlog.map((t) => (
                    <div className="activity-backlog" key={t.id}>
                      <b>{t.name}</b>
                      <span>{t.blocking_reason || "等待安排"}</span>
                    </div>
                  ))}
                </section>
              )}
              <AIAnalysis
                key={root + plan.id}
                root={root}
                sourceKind="daily_plan"
                sourceId={plan.id}
              />
            </>
          )}
        </div>
        <aside className="activity-stack">
          <Reviews
            root={root}
            dueOnly
            onStarted={onReviewStarted}
            onViewAll={onViewReviews}
          />
          <section className="card activity-suggestions" aria-label="计划建议">
            <span className="eyebrow">根据学习进展调整安排</span>
            <h3>计划建议</h3>
            <ActivityError message={suggestions.error} />
            {suggestions.loading && !suggestions.data && (
              <p className="muted">正在读取计划建议…</p>
            )}
            {suggestions.data &&
              !suggestions.data.some((s) => s.status === "pending") && (
                <p className="muted">
                  当前没有待处理的调整建议，可继续完成今天的任务。
                </p>
              )}
            {suggestions.data
              ?.filter((s) => s.status === "pending")
              .map((s) => (
                <article key={s.id}>
                  <h4>{s.title}</h4>
                  <p>{s.reason}</p>
                  <div className="button-row">
                    <ActionButton
                      loadingText="正在应用建议…"
                      disabled={!!busy}
                      onClick={() =>
                        mutate("accept:" + s.id, `/suggestions/${s.id}/accept`)
                      }
                    >
                      接受建议
                    </ActionButton>
                    <ActionButton
                      loadingText="正在保存…"
                      disabled={!!busy}
                      className="text-button"
                      onClick={() =>
                        mutate("dismiss:" + s.id, `/suggestions/${s.id}/skip`)
                      }
                    >
                      跳过
                    </ActionButton>
                  </div>
                </article>
              ))}
            <p className="small muted">
              跳过或改期只调整任务安排。知识掌握情况和下次复习时间会根据实际作答更新。
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
