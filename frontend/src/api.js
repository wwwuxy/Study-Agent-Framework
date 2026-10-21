let sessionGeneration = 0;
const expirationListeners = new Set();
export function advanceSessionScope() {
  return ++sessionGeneration;
}
export function onSessionExpired(handler) {
  expirationListeners.add(handler);
  return () => expirationListeners.delete(handler);
}

export async function api(path, options = {}) {
  const generation = sessionGeneration;
  const response = await fetch("/api/v1" + path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
    body:
      options.rawBody !== undefined
        ? options.rawBody
        : options.body === undefined
          ? undefined
          : JSON.stringify(options.body),
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (
    response.status === 401 &&
    generation === sessionGeneration &&
    !["/auth/login", "/auth/register", "/auth/me"].includes(path)
  ) {
    for (const listener of expirationListeners) listener();
  }
  if (!response.ok)
    throw new Error(data.error?.message || "请求失败，请稍后重试");
  return data;
}
export const key = () => crypto.randomUUID();
