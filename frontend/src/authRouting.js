export function authRoute(pathname) {
  if (pathname === "/login") return "login";
  if (pathname === "/register") return "register";
  return "workspace";
}

export function navigateAuth(mode, { replace = false } = {}) {
  const path = { login: "/login", register: "/register", workspace: "/" }[mode];
  if (!path || window.location.pathname === path) return;
  window.history[replace ? "replaceState" : "pushState"](null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
