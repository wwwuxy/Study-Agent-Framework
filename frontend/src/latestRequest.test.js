import test from "node:test";
import assert from "node:assert/strict";
import { createLatestRequest } from "./latestRequest.js";

test("late space A cannot overwrite the completed request for space B", async () => {
  const gate = createLatestRequest();
  let resolveA;
  const screen = [];
  const a = gate.run(
    () =>
      new Promise((resolve) => {
        resolveA = resolve;
      }),
    (value) => screen.push(value),
  );
  await gate.run(
    async () => "space B",
    (value) => screen.push(value),
  );
  resolveA("space A");
  await a;
  assert.deepEqual(screen, ["space B"]);
});

test("logout invalidates pending responses before another account signs in", async () => {
  const gate = createLatestRequest();
  let resolve;
  const screen = [];
  const request = gate.run(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
    (value) => screen.push(value),
  );
  gate.invalidate();
  resolve("previous account data");
  await request;
  assert.deepEqual(screen, []);
});

test("a stale mutation cannot start fresh reads in a new login session", async () => {
  const session = createLatestRequest();
  const reads = createLatestRequest();
  const isCurrent = session.checkpoint();
  let finish;
  const screen = [];
  const operation = (async () => {
    const result = await new Promise((resolve) => {
      finish = resolve;
    });
    if (!isCurrent()) return;
    await reads.run(
      async () => result,
      (value) => screen.push(value),
    );
  })();
  session.invalidate();
  finish("old account space");
  await operation;
  assert.deepEqual(screen, []);
});
