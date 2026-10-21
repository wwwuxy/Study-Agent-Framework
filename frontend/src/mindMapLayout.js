const WIDTH = 224;
const HEIGHT = 92;
const ROW = 124;

// A spanning tree gives every concept one location; the remaining DAG edges
// stay visible as secondary links rather than duplicating concepts.
export function buildMindMap(concepts) {
  const nodes = concepts.map((concept) => ({
    ...concept,
    width: WIDTH,
    height: HEIGHT,
    depth: 1,
    parent: null,
  }));
  const byKey = new Map(nodes.map((node) => [node.key, node]));
  const resolved = new Set();
  let pending = [...nodes];
  while (pending.length) {
    let progressed = false;
    const next = [];
    for (const node of pending) {
      const parents = [...new Set(node.prerequisites || [])].filter(
        (key) => byKey.has(key) && key !== node.key,
      );
      if (parents.some((key) => !resolved.has(key))) {
        next.push(node);
        continue;
      }
      const parent = parents
        .map((key) => byKey.get(key))
        .sort((a, b) => b.depth - a.depth)[0];
      node.parent = parent?.key ?? null;
      node.depth = parent ? parent.depth + 1 : 1;
      resolved.add(node.key);
      progressed = true;
    }
    // Valid server graphs are DAGs. Keep the canvas usable for a damaged graph.
    if (!progressed && next.length) resolved.add(next.shift().key);
    pending = next;
  }
  const children = new Map([[null, []], ...nodes.map((n) => [n.key, []])]);
  for (const node of nodes) children.get(node.parent).push(node);
  const weight = (node) =>
    Math.max(
      1,
      children.get(node.key).reduce((sum, child) => sum + weight(child), 0),
    );
  const sides = [[], []];
  const weights = [0, 0];
  children.get(null).forEach((node, branch) => {
    const side = weights[0] <= weights[1] ? 0 : 1;
    sides[side].push({ node, branch });
    weights[side] += weight(node);
  });
  const place = (node, side, start, branch) => {
    const span = weight(node) * ROW;
    node.x = side * (node.depth * 320 + 20);
    node.y = start + span / 2;
    node.side = side;
    node.branch = branch;
    let cursor = start;
    for (const child of children.get(node.key)) {
      place(child, side, cursor, branch);
      cursor += weight(child) * ROW;
    }
  };
  sides.forEach((roots, index) => {
    let cursor = (-weights[index] * ROW) / 2;
    for (const { node, branch } of roots) {
      place(node, index === 0 ? 1 : -1, cursor, branch);
      cursor += weight(node) * ROW;
    }
  });
  const edges = [];
  for (const node of nodes) {
    if (node.parent === null)
      edges.push({ from: null, to: node.key, secondary: false });
    for (const key of new Set(node.prerequisites || [])) {
      if (byKey.has(key) && key !== node.key) {
        edges.push({ from: key, to: node.key, secondary: key !== node.parent });
      }
    }
  }
  const left = Math.min(-122, ...nodes.map((n) => n.x - n.width / 2));
  const right = Math.max(122, ...nodes.map((n) => n.x + n.width / 2));
  const top = Math.min(-56, ...nodes.map((n) => n.y - n.height / 2));
  const bottom = Math.max(56, ...nodes.map((n) => n.y + n.height / 2));
  let lane = 0;
  for (const edge of edges) {
    if (edge.secondary) edge.laneY = top - 48 - (lane++ % 3) * 12;
  }
  const linkTop = Math.min(
    top,
    ...edges.filter((edge) => edge.secondary).map((edge) => edge.laneY),
  );
  return {
    nodes,
    edges,
    bounds: {
      x: left - 24,
      y: linkTop - 24,
      width: right - left + 48,
      height: bottom - linkTop + 48,
    },
  };
}

export function fitMindMap(bounds, width, height) {
  const scale = Math.min(
    1,
    Math.max(1, width - 40) / bounds.width,
    Math.max(1, height - 40) / bounds.height,
  );
  return {
    scale,
    x: width / 2 - (bounds.x + bounds.width / 2) * scale,
    y: height / 2 - (bounds.y + bounds.height / 2) * scale,
  };
}

export function zoomMindMap(view, factor, point) {
  const scale = Math.max(0.01, Math.min(2.5, view.scale * factor));
  const ratio = scale / view.scale;
  return {
    scale,
    x: point.x - (point.x - view.x) * ratio,
    y: point.y - (point.y - view.y) * ratio,
  };
}
