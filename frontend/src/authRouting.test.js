import test from "node:test";
import assert from "node:assert/strict";
import { authRoute } from "./authRouting.js";
import { api, advanceSessionScope, onSessionExpired } from "./api.js";

test("login and register resolve only to local authentication views", () => {
  assert.equal(authRoute("/login"), "login");
  assert.equal(authRoute("/register"), "register");
  assert.equal(authRoute("/"), "workspace");
  assert.equal(authRoute("https://other.example/login"), "workspace");
});

test("a late401 from account A never expires the new account B session", async () => {
  const oldFetch = globalThis.fetch;
  let reply;
  let expired = 0;
  const unsubscribe = onSessionExpired(() => expired++);
  globalThis.fetch = () =>
    new Promise((resolve) => {
      reply = resolve;
    });
  try {
    const pending = api("/study-spaces");
    advanceSessionScope();
    reply(
      new Response(JSON.stringify({ error: { message: "expired" } }), {
        status: 401,
      }),
    );
    await assert.rejects(pending);
    assert.equal(expired, 0);
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ error: { message: "expired" } }), {
        status: 401,
      });
    await assert.rejects(api("/study-spaces"));
    assert.equal(expired, 1);
  } finally {
    unsubscribe();
    globalThis.fetch = oldFetch;
  }
});

test('an anonymous bootstrap check preserves the registration route', async () => {
  const oldFetch = globalThis.fetch;
  let redirected = 0;
  const unsubscribe = onSessionExpired(() => redirected++);
  globalThis.fetch = async () => new Response(JSON.stringify({error:{message:'anonymous'}}),{status:401});
  try {
    await assert.rejects(api('/auth/me'));
    assert.equal(redirected, 0);
  } finally { unsubscribe(); globalThis.fetch = oldFetch; }
});
