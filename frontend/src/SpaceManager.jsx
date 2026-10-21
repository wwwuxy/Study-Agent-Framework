import ActionButton from "./ActionButton";
import React, { useEffect, useRef, useState } from "react";
import { ArrowRight, Layers, Plus, RotateCcw, Trash2 } from "lucide-react";
import { api, key } from "./api";
import { createLatestRequest } from "./latestRequest";

export default function SpaceManager({
  embedded = false,
  currentSpaceId,
  providers,
  onOpen,
  onCreate,
  onRemove,
}) {
  const [spaces, setSpaces] = useState([]);
  const [cleanup, setCleanup] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const reads = useRef(createLatestRequest());
  const mounted = useRef(true);
  const cancelButton = useRef(null);

  async function reload() {
    await reads.current.run(
      () =>
        Promise.all([
          api("/study-spaces?include_archived=true"),
          api("/study-spaces/deletion-jobs"),
        ]),
      ([items, jobs]) => {
        setSpaces(items);
        setCleanup(jobs);
      },
    );
  }
  useEffect(() => {
    mounted.current = true;
    reload()
      .catch((err) => {
        if (mounted.current) setError(err.message);
      })
      .finally(() => {
        if (mounted.current) setLoading(false);
      });
    return () => {
      mounted.current = false;
      reads.current.invalidate();
    };
  }, []);
  useEffect(() => {
    if (pending) cancelButton.current?.focus();
  }, [pending]);
  useEffect(() => {
    if (!cleanup.some((job) => ["queued", "running"].includes(job.status)))
      return;
    const timer = setInterval(() => {
      if (!busy)
        reload().catch((err) => {
          if (mounted.current) setError(err.message);
        });
    }, 3000);
    return () => clearInterval(timer);
  }, [cleanup, busy]);

  async function remove() {
    setBusy(true);
    setError("");
    reads.current.invalidate();
    try {
      const changed = await onRemove(pending.id);
      if (!mounted.current || changed === false) return;
      setSpaces((items) => items.filter((item) => item.id !== pending.id));
      setPending(null);
      try {
        await reload();
      } catch (err) {
        if (mounted.current)
          setError("空间已永久删除，但清理状态刷新失败：" + err.message);
      }
    } catch (err) {
      if (mounted.current) setError(err.message);
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function retry(job) {
    setBusy(true);
    setError("");
    try {
      const updated = await api("/jobs/" + job.id + "/retry", {
        method: "POST",
        body: { idempotency_key: key() },
      });
      if (!mounted.current) return;
      setCleanup((items) =>
        items.map((item) => (item.id === job.id ? updated : item)),
      );
      await reload();
    } catch (err) {
      if (mounted.current) setError(err.message);
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  const active = spaces.filter((space) => space.status !== "archived");
  const archived = spaces.filter((space) => space.status === "archived");
  function row(space) {
    const isArchived = space.status === "archived";
    const provider = providers.find((item) => item.id === space.provider_id);
    return (
      <article className="card managed-space" key={space.id}>
        <div className="managed-space-title">
          <h3>{space.goal}</h3>
          {space.id === currentSpaceId && !isArchived && (
            <span className="tag green">当前空间</span>
          )}
          {isArchived && <span className="tag">此前已移除</span>}
        </div>
        <p className="muted small">
          教学模型：{provider?.name || "未找到模型连接"}
        </p>
        <p className="muted small">
          创建于 {new Date(space.created_at).toLocaleDateString("zh-CN")}
        </p>
        <div className="button-row">
          {!isArchived && (
            <button disabled={busy} onClick={() => onOpen(space.id)}>
              进入学习 <ArrowRight size={15} />
            </button>
          )}
          <button
            className="danger"
            disabled={busy}
            onClick={() => {
              setError("");
              setPending(space);
            }}
          >
            <Trash2 size={15} /> 删除空间
          </button>
        </div>
      </article>
    );
  }
  return (
    <>
      <div className="space-manager-heading">
        <div>
          {!embedded && (
            <span className="eyebrow">按目标整理课程、教材与学习进度</span>
          )}
          {embedded ? <h2>学习空间管理</h2> : <h1>学习空间</h1>}
          <p className="muted">
            整理你的学习目标，继续学习或永久删除不再需要的空间。
          </p>
        </div>
        <button className="primary" onClick={onCreate} disabled={busy}>
          <Plus size={16} /> 新建学习空间
        </button>
      </div>
      {error && !pending && (
        <div className="error" role="alert">
          {error}
          <ActionButton
            loadingText="正在刷新…"
            disabled={busy}
            onClick={() =>
              reload()
                .then(() => setError(""))
                .catch((err) => setError(err.message))
            }
          >
            刷新状态
          </ActionButton>
        </div>
      )}
      {loading ? (
        <p role="status">正在读取学习空间…</p>
      ) : (
        <>
          {active.length ? (
            <div className="managed-space-grid">{active.map(row)}</div>
          ) : (
            <section className="card space-manager-empty">
              <Layers size={36} />
              <h3>还没有学习空间</h3>
              <p className="muted">创建一个学习目标，开始新的学习。</p>
            </section>
          )}
          {!!archived.length && (
            <section className="removed-spaces">
              <h2>此前已移除的空间</h2>
              <p className="muted small">
                这些旧空间尚未清除内容，可在此确认永久删除。
              </p>
              <div className="managed-space-grid">{archived.map(row)}</div>
            </section>
          )}
          {!!cleanup.length && (
            <section className="removed-spaces">
              <h2>远端教材清理</h2>
              <p className="muted small">
                本地教材和学习记录已删除。远端文件正在清理；若凭证已变更，请恢复原配置后重试，或到服务商控制台删除文件。远端保留以服务商政策为准。
              </p>
              <div className="managed-space-grid">
                {cleanup.map((job) => (
                  <article className="card managed-space" key={job.id}>
                    <h3>已删除空间 · {job.space_id.slice(0, 8)}</h3>
                    <p className="muted small">
                      教材标识：{job.asset_id.slice(0, 8)}
                    </p>
                    <p role="status">
                      {job.stage === "waiting_upload"
                        ? "等待正在上传的文件返回后清理"
                        : job.status === "failed"
                          ? "远端清理失败"
                          : job.status === "running"
                            ? "正在清理远端文件…"
                            : "等待后台清理"}
                    </p>
                    {job.error_message && (
                      <p className="error">{job.error_message}</p>
                    )}
                    {job.status === "failed" && (
                      <ActionButton
                        loadingText="正在重试清理…"
                        disabled={busy}
                        onClick={() => retry(job)}
                      >
                        <RotateCcw size={15} /> 重试清理
                      </ActionButton>
                    )}
                  </article>
                ))}
              </div>
              <ActionButton
                loadingText="正在刷新清理状态…"
                disabled={busy}
                onClick={() => reload().catch((err) => setError(err.message))}
              >
                刷新清理状态
              </ActionButton>
            </section>
          )}
        </>
      )}
      {pending && (
        <div
          className="modal-backdrop"
          onClick={() => {
            if (!busy) setPending(null);
          }}
        >
          <div
            className="modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="remove-space-title"
            aria-describedby="remove-space-description"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape" && !busy) setPending(null);
            }}
          >
            <h2 id="remove-space-title">永久删除学习空间？</h2>
            <p className="managed-space-goal">{pending.goal}</p>
            <p id="remove-space-description" className="muted">
              学习记录、课程、答题内容和本地教材将永久删除，无法恢复。正在处理的教材任务会停止，远端教材将进入清理队列，失败后可在本页重试。
            </p>
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <div className="button-row">
              <button
                ref={cancelButton}
                disabled={busy}
                onClick={() => setPending(null)}
              >
                取消
              </button>
              <ActionButton
                loadingText="正在删除空间…"
                className="danger"
                disabled={busy}
                onClick={remove}
              >
                {busy ? "正在删除…" : "确认永久删除"}
              </ActionButton>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
