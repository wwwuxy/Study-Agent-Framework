import assert from "node:assert/strict";
import { test } from "node:test";
import { createPlanningChatState, shouldSend } from "./planningChatState.js";

test("duplicate send and retry keep one message key", async () => {
  const gate = createPlanningChatState(() => "stable");
  let resolve,
    calls = 0;
  const load = (body) => {
    calls++;
    assert.equal(body.idempotency_key, "stable");
    return new Promise((r) => (resolve = r));
  };
  const a = gate.runSend("hello", load, () => {}),
    b = gate.runSend("hello", load, () => {});
  assert.equal(calls, 1);
  resolve({ status: "completed" });
  await Promise.all([a, b]);
  await gate.runSend(
    "hello",
    async (body) => {
      assert.equal(body.retry, true);
      assert.equal(body.idempotency_key, "stable");
      return { status: "completed" };
    },
    () => {},
    true,
  );
});
test("old space cannot publish and committed result survives refresh failure", async () => {
  const gate = createPlanningChatState(() => "stable");
  let resolve,
    published = false;
  const work = gate.runSend(
    "hello",
    () => new Promise((r) => (resolve = r)),
    () => {
      published = true;
    },
  );
  gate.invalidate();
  resolve({ status: "completed" });
  await work;
  assert.equal(published, false);
  let result;
  await assert.rejects(
    gate.runSend(
      "new",
      async () => ({ id: "saved" }),
      (v) => {
        result = v;
        throw Error("refresh");
      },
    ),
    /refresh/,
  );
  assert.equal(result.id, "saved");
});
test("IME composition never sends, Ctrl/Cmd Enter sends", () => {
  assert.equal(
    shouldSend({ key: "Enter", ctrlKey: true, isComposing: true }),
    false,
  );
  assert.equal(shouldSend({ key: "Enter", metaKey: true }), true);
  assert.equal(shouldSend({ key: "Enter" }), false);
});
