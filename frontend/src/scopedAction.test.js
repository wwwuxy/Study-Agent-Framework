import test from "node:test";
import assert from "node:assert/strict";
import { createScopedAction } from "./scopedAction.js";

test("duplicate review starts share one pending operation", async () => {
  const gate = createScopedAction();
  let finish;
  const screen = [];
  const first = gate.run(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
    (v) => screen.push(v),
  );
  const duplicate = gate.run(
    async () => "unwanted second review",
    (v) => screen.push(v),
  );
  finish("the original review");
  await Promise.all([first, duplicate]);
  assert.deepEqual(screen, ["the original review"]);
});

test("old account review completion cannot replace a new account screen", async () => {
  const gate = createScopedAction();
  let finish;
  const screen = [];
  const old = gate.run(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
    (v) => screen.push(v),
  );
  gate.invalidate();
  await gate.run(
    async () => "new account",
    (v) => screen.push(v),
  );
  finish("old private review");
  await old;
  assert.deepEqual(screen, ["new account"]);
});
