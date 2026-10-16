export async function api(path, options = {}) {
  const response = await fetch("/api/v1" + path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error?.message || "请求失败，请稍后重试");
  return data;
}
export const key = () => crypto.randomUUID();
