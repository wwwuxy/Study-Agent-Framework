import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { createActivityActions } from "./activityState";

export function useActivityResource(url) {
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const version = useRef(0);
  const actions = useRef(createActivityActions());
  async function reload() {
    const current = ++version.current;
    setLoading(true);
    try {
      const value = await api(url);
      if (current === version.current) {
        setData(value);
        setError("");
      }
    } catch (e) {
      if (current === version.current) setError(e.message);
      throw e;
    } finally {
      if (current === version.current) setLoading(false);
    }
  }
  async function more() {
    if (!data?.next_cursor) return;
    const current = version.current;
    try {
      const result = await api(
        url +
          (url.includes("?") ? "&" : "?") +
          "cursor=" +
          encodeURIComponent(data.next_cursor),
      );
      if (current === version.current)
        setData((old) => ({
          ...result,
          items: [
            ...old.items,
            ...result.items.filter(
              (n) => !old.items.some((p) => p.id === n.id),
            ),
          ],
        }));
    } catch (e) {
      if (current === version.current) setError(e.message);
    }
  }
  useEffect(() => {
    setData(null);
    setError("");
    reload().catch(() => {});
    return () => {
      version.current++;
      actions.current.invalidate();
    };
  }, [url]);
  return {
    data,
    error,
    setError,
    loading,
    reload,
    more,
    actions: actions.current,
  };
}

export function ActivityError({ message }) {
  return message ? (
    <div className="error" role="alert">
      {message}
    </div>
  ) : null;
}
export const activityStatus = {
  pending: "待开始",
  in_progress: "进行中",
  completed: "已完成",
  skipped: "已跳过",
  postponed: "已改期",
  superseded: "已更新",
  processing: "分析中",
  failed: "分析失败",
  conflict: "配置已变更",
  queued: "排队中",
  running: "执行中",
  retry_wait: "等待重试",
  succeeded: "已完成",
  dead_letter: "失败终止",
  cancelled: "已取消",
  accepted: "已接受",
  expired: "已过期",
};
