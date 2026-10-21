import test from "node:test";
import assert from "node:assert/strict";
import { buildMindMap, fitMindMap, zoomMindMap } from "./mindMapLayout.js";

const concept = (key, prerequisites = []) => ({
  key,
  name: key,
  prerequisites,
});

test("shared prerequisite links survive without duplicating knowledge nodes", () => {
  const map = buildMindMap([
    concept("advanced", ["foundation", "practice"]),
    concept("foundation"),
    concept("practice", ["foundation"]),
    concept("independent"),
  ]);
  assert.deepEqual(map.nodes.map((n) => n.key).sort(), [
    "advanced",
    "foundation",
    "independent",
    "practice",
  ]);
  assert.deepEqual(
    map.edges.map((e) => [e.from, e.to, e.secondary]).sort(),
    [
      [null, "foundation", false],
      [null, "independent", false],
      ["foundation", "practice", false],
      ["practice", "advanced", false],
      ["foundation", "advanced", true],
    ].sort(),
  );
  const advanced = map.nodes.find((n) => n.key === "advanced");
  const practice = map.nodes.find((n) => n.key === "practice");
  assert.ok(Math.abs(advanced.x) > Math.abs(practice.x));
});

test("independent branches spread to both sides without overlapping nodes", () => {
  const map = buildMindMap(
    Array.from({ length: 12 }, (_, i) => concept(`root${i}`)),
  );
  assert.ok(map.nodes.some((n) => n.x < 0));
  assert.ok(map.nodes.some((n) => n.x > 0));
  for (const [i, a] of map.nodes.entries()) {
    for (const b of map.nodes.slice(i + 1)) {
      assert.ok(
        Math.abs(a.x - b.x) >= a.width || Math.abs(a.y - b.y) >= a.height,
      );
    }
  }
});

test("extra prerequisite links route outside intermediate nodes and stay in fit bounds", () => {
  const map = buildMindMap([
    concept("a"),
    concept("b", ["a"]),
    concept("c", ["a", "b"]),
  ]);
  const link = map.edges.find((edge) => edge.from === "a" && edge.to === "c");
  for (const node of map.nodes)
    assert.ok(link.laneY < node.y - node.height / 2);
  assert.ok(map.bounds.y <= link.laneY);
});

test("all 60 nodes of a deep curriculum remain finite and inside the map bounds", () => {
  const map = buildMindMap(
    Array.from({ length: 60 }, (_, i) =>
      concept(`c${i}`, i ? [`c${i - 1}`] : []),
    ),
  );
  assert.equal(map.nodes.length, 60);
  assert.equal(map.edges.length, 60);
  for (const n of map.nodes) {
    assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y));
    assert.ok(n.x - n.width / 2 >= map.bounds.x);
    assert.ok(n.x + n.width / 2 <= map.bounds.x + map.bounds.width);
    assert.ok(n.y - n.height / 2 >= map.bounds.y);
    assert.ok(n.y + n.height / 2 <= map.bounds.y + map.bounds.height);
  }
});

test("an empty curriculum keeps a finite goal canvas", () => {
  const map = buildMindMap([]);
  assert.deepEqual(map.nodes, []);
  assert.deepEqual(map.edges, []);
  assert.ok(map.bounds.width > 0 && map.bounds.height > 0);
});

test("fit keeps the entire map inside a narrow phone viewport", () => {
  const bounds = { x: -500, y: -300, width: 1600, height: 1000 };
  const view = fitMindMap(bounds, 358, 480);
  assert.ok(bounds.x * view.scale + view.x >= 20);
  assert.ok(bounds.y * view.scale + view.y >= 20);
  assert.ok((bounds.x + bounds.width) * view.scale + view.x <= 338);
  assert.ok((bounds.y + bounds.height) * view.scale + view.y <= 460);
});

test("zoom stays anchored at the chosen screen point", () => {
  const view = zoomMindMap({ x: 100, y: 50, scale: 1 }, 2, { x: 200, y: 150 });
  assert.deepEqual(view, { x: 0, y: -50, scale: 2 });
  const limited = zoomMindMap(view, 100, { x: 200, y: 150 });
  assert.ok(limited.scale <= 2.5);
});
