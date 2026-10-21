import test from "node:test";
import assert from "node:assert/strict";
import { createExamDiagnosticState } from "./examDiagnosticState.js";

const files = [
  { name: "one.png", type: "image/png", size: 3 },
  { name: "two.png", type: "image/png", size: 4 },
];

test("deleting a diagnostic prevents a late poll from restoring it", async () => {
  let finishPoll;
  const visible = [];
  const controller = createExamDiagnosticState({
    api: async (path, options = {}) => {
      if (options.method === "DELETE") {
        assert.equal(path, "/s/exam-diagnostics/e");
        return null;
      }
      return new Promise((resolve) => {
        finishPoll = resolve;
      });
    },
  });
  const pending = controller.poll("/s", "e", (value) => visible.push(value));
  await controller.remove("/s", { id: "e" }, () => visible.push("deleted"));
  finishPoll({ id: "e", status: "running" });
  await pending;
  assert.deepEqual(visible, ["deleted"]);
});

test("upload starts only after every attachment is saved", async () => {
  const calls = [];
  const controller = createExamDiagnosticState({
    makeKey: () => "key",
    hashFile: async (f) => f.name,
    api: async (path, options = {}) => {
      calls.push([path, options]);
      if (path.endsWith("/exam-diagnostics") && options.method === "POST")
        return {
          id: "e",
          status: "draft",
          attachments: [
            { id: "a1", client_id: "a1", received: false },
            { id: "a2", client_id: "a2", received: false },
          ],
        };
      return { id: "e", status: path.endsWith("/start") ? "queued" : "draft" };
    },
  });
  await controller.upload("/space", files, { name: "paper" }, true, () => {});
  assert.deepEqual(
    calls.map(([path, o]) => o.method),
    ["POST", "PUT", "PUT", "POST"],
  );
  assert.equal(calls[3][1].body.consent, true);
});

test("switching scope stops late mutations and callbacks", async () => {
  let resolve;
  const events = [];
  const controller = createExamDiagnosticState({
    makeKey: () => "key",
    hashFile: async () => "hash",
    api: async () =>
      new Promise((r) => {
        resolve = r;
      }),
  });
  const pending = controller.upload("/old", files.slice(0, 1), {}, true, (r) =>
    events.push(r),
  );
  await new Promise((r) => setTimeout(r, 0));
  controller.invalidate();
  resolve({
    id: "old",
    status: "draft",
    attachments: [{ id: "a", client_id: "a1", received: false }],
  });
  await pending;
  assert.deepEqual(events, []);
});

test("failed upload does not start diagnosis and retry keeps request identity", async () => {
  const keys = [];
  let fail = true;
  let started = 0;
  const controller = createExamDiagnosticState({
    makeKey: () => String(keys.length),
    hashFile: async () => "hash",
    api: async (path, o) => {
      if (o.method === "POST" && !path.endsWith("/start")) {
        keys.push(o.body.idempotency_key);
        return {
          id: "e",
          status: "draft",
          attachments: [{ id: "a", client_id: "a1", received: false }],
        };
      }
      if (o.method === "PUT" && fail) throw new Error("network");
      if (path.endsWith("/start")) started++;
      return { id: "e", status: "queued" };
    },
  });
  await assert.rejects(() =>
    controller.upload("/space", files.slice(0, 1), {}, true, () => {}),
  );
  assert.equal(started, 0);
  fail = false;
  await controller.upload("/space", files.slice(0, 1), {}, true, () => {});
  assert.equal(keys[0], keys[1]);
  assert.equal(started, 1);
});

test("acknowledged retry can be retried after another failure, uncertain request keeps identity", async () => {
  let keys = 0;
  const requests = [];
  let uncertain = true;
  const controller = createExamDiagnosticState({
    makeKey: () => "key" + ++keys,
    api: async (path, o) => {
      requests.push(o.body.idempotency_key);
      if (uncertain) throw new Error("network outcome unknown");
      return { id: "e", version: 1, status: "queued" };
    },
  });
  const failed = { id: "e", version: 1, status: "failed" };
  await assert.rejects(() =>
    controller.action("/s", failed, "retry", true, () => {}),
  );
  uncertain = false;
  await controller.action("/s", failed, "retry", true, () => {});
  await controller.action("/s", failed, "retry", true, () => {});
  assert.equal(requests[0], requests[1]);
  assert.notEqual(requests[1], requests[2]);
});
