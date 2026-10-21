import ActionButton from "./ActionButton";
import React, { useEffect, useState } from "react";
import { Sparkles, RefreshCw } from "lucide-react";
import { api } from "./api";
import { useActivityResource, ActivityError } from "./useActivity";

export default function AIAnalysis({ root, sourceKind, sourceId }) {
  const resource = useActivityResource(root + "/analyses");
  const [result, setResult] = useState(null),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (resource.data)
      setResult(
        resource.data.items.find(
          (r) => r.source_kind === sourceKind && r.source_id === sourceId,
        ) || null,
      );
  }, [resource.data, sourceKind, sourceId]);
  useEffect(() => {
    if (!result || result.status !== "processing" || result.retry_allowed)
      return;
    let active = true;
    const timer = setInterval(async () => {
      try {
        const r = await api(root + "/analyses/" + result.id);
        if (active) setResult(r);
      } catch (e) {
        if (active) resource.setError(e.message);
      }
    }, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [root, result?.id, result?.status, result?.retry_allowed]);
  async function analyze() {
    const current = resource.actions.checkpoint();
    setBusy(true);
    resource.setError("");
    const retry = result?.retry_allowed ? result.id : null;
    try {
      const response = await resource.actions.run(
        "analysis:" + (result?.id || "new"),
        (body) =>
          api(root + "/analyses", {
            method: "POST",
            body: {
              ...body,
              source_kind: sourceKind,
              source_id: sourceId,
              ...(retry ? { retry_of: retry } : {}),
            },
          }),
      );
      if (response.current) setResult(response.value);
    } catch (e) {
      if (current()) resource.setError(e.message);
    } finally {
      if (current()) setBusy(false);
    }
  }
  const processing = result?.status === "processing" && !result.retry_allowed;
  return (
    <section className="card activity-ai">
      <div className="section-head">
        <h3>
          <Sparkles size={18} /> 看见数据背后的线索
        </h3>
        <span className="tag">AI 分析</span>
      </div>
      <p className="small muted">
        使用当前空间的模型解读学习记录、提供改进建议。仅在点击后调用，可能产生费用，并计入每日分析额度。
      </p>
      <ActivityError message={resource.error} />
      {result?.content && (
        <div className="activity-ai-content">
          <p>{result.content.summary}</p>
          <ul>
            {result.content.recommendations.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
          {result.content.caveats.map((s, i) => (
            <p className="small muted" key={i}>
              {s}
            </p>
          ))}
        </div>
      )}
      {result?.error_message && <p className="hint">{result.error_message}</p>}
      {result && (
        <p className="small muted">
          {result.is_demo ? "固定离线演示 · " : ""}
          {result.usage_status === "reported"
            ? `实际 ${result.actual_tokens} Token`
            : `预留 ${result.reserved_tokens} Token · ${result.usage_status === "pending" ? "处理中" : "用量未返回，暂按预留额度计入"}`}
        </p>
      )}
      <ActionButton
        loadingText={
          resource.loading ? "正在读取分析记录…" : "正在分析学习记录…"
        }
        className="primary"
        disabled={busy || processing || resource.loading}
        loading={busy || processing || resource.loading}
        onClick={analyze}
      >
        <Sparkles size={15} />
        {busy || processing
          ? "正在分析…"
          : result?.retry_allowed
            ? "重试分析（计入额度）"
            : result?.content
              ? "重新分析（计入额度）"
              : "生成 AI 分析"}
      </ActionButton>
      {resource.error && (
        <ActionButton
          loadingText="正在读取分析结果…"
          className="text-button"
          onClick={() => resource.reload().catch(() => {})}
        >
          <RefreshCw size={14} /> 刷新分析结果
        </ActionButton>
      )}
    </section>
  );
}
