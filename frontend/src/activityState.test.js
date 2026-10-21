import test from "node:test";
import assert from "node:assert/strict";
import { createActivityActions } from "./activityState.js";

test("duplicate activity mutations share one pending request identity", async () => {
  const state = createActivityActions();
  let release;
  let count = 0;
  const call = (body) => {
    count++;
    assert.ok(body.idempotency_key);
    return new Promise((resolve) => {
      release = resolve;
    });
  };
  const first = state.run("start:task", call);
  const second = state.run("start:task", call);
  assert.equal(count, 1);
  release("started");
  assert.equal((await first).value, "started");
  assert.equal((await second).current, true);
});

test("an account switch invalidates late activity results and analysis retry has a new key", async () => {
  const state = createActivityActions();
  let release;
  const keys = [];
  const pending = state.run("analysis:one", (body) => {
    keys.push(body.idempotency_key);
    return new Promise((resolve) => {
      release = resolve;
    });
  });
  state.invalidate();
  release("old account");
  assert.equal((await pending).current, false);
  await state.run("retry:old-run", async (body) => {
    keys.push(body.idempotency_key);
    return "retry";
  });
  assert.notEqual(keys[0], keys[1]);
});
