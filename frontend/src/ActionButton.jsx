import React, { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";

export function LoadingNotice({ active = true, children }) {
  if (!active) return null;
  return (
    <span className="loading-inline" role="status">
      <LoaderCircle size={15} className="spin" aria-hidden="true" />
      <span>{children}</span>
    </span>
  );
}

// Keep feedback on the button that initiated the request, not on every disabled button.
export default function ActionButton({
  children,
  onClick,
  loading = false,
  loadingText = "正在处理…",
  disabled = false,
  ...props
}) {
  const [pending, setPending] = useState(false);
  const locked = useRef(false),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const active = loading || pending;
  async function click(event) {
    if (disabled || active || locked.current || !onClick) return;
    locked.current = true;
    setPending(true);
    try {
      await onClick(event);
    } finally {
      locked.current = false;
      if (mounted.current) setPending(false);
    }
  }
  return (
    <button
      {...props}
      disabled={disabled || active}
      aria-busy={active || undefined}
      aria-label={active ? loadingText : props["aria-label"]}
      onClick={click}
    >
      {active ? <LoadingNotice>{loadingText}</LoadingNotice> : children}
    </button>
  );
}
