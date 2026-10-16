import assert from "node:assert/strict";
import { test } from "node:test";
import { api } from "./api.js";

test("PDF upload preserves binary body and explicit transfer headers", async () => {
  const original = globalThis.fetch;
  const file = new Blob(["%PDF-binary"], { type: "application/pdf" });
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/v1/study-spaces/owned/materials");
    assert.equal(options.body, file);
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.headers["X-File-Consent"], "true");
    assert.equal(options.headers["Content-Type"], "application/pdf");
    return { status: 202, ok: true, json: async () => ({ status: "queued" }) };
  };
  try {
    assert.deepEqual(
      await api("/study-spaces/owned/materials", {
        method: "POST",
        rawBody: file,
        headers: {
          "Content-Type": "application/pdf",
          "X-File-Consent": "true",
        },
      }),
      { status: "queued" },
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("normal API requests retain JSON encoding and show structured errors", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (_, options) => {
    assert.equal(options.body, '{"consent":false}');
    return {
      status: 422,
      ok: false,
      json: async () => ({ error: { message: "需要上传授权" } }),
    };
  };
  try {
    await assert.rejects(
      api("/x", { method: "POST", body: { consent: false } }),
      /需要上传授权/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
