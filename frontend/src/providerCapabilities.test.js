import test from "node:test";
import assert from "node:assert/strict";
import { providerCapabilityLabels } from "./providerCapabilities.js";

test("image support is visible independently of PDF support", () => {
  const labels = providerCapabilityLabels({
    tested: true,
    provider_type: "openai_compatible",
    capabilities: {
      chat: true,
      image_input: true,
      supported_image_mime_types: ["image/png", "image/jpeg"],
      file_input: false,
    },
  });
  assert.equal(labels.image, "已验证（PNG、JPEG）");
  assert.equal(labels.pdf, "当前连接未接入");
});

test("old capability records require a new image test", () => {
  assert.equal(
    providerCapabilityLabels({ tested: true, capabilities: { chat: true } })
      .image,
    "未检测（请重新检测）",
  );
});

test("failed image tests do not claim the model cannot see images", () => {
  assert.equal(
    providerCapabilityLabels({
      tested: true,
      capabilities: { image_input: false },
    }).image,
    "检测未通过",
  );
});

test("untested connections do not display stale verified capabilities", () => {
  const labels = providerCapabilityLabels({
    tested: false,
    capabilities: { image_input: true, file_input: true },
  });
  assert.equal(labels.image, "待检测");
  assert.equal(labels.pdf, "待检测");
});
