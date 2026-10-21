import React, {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowRight,
  BookOpen,
  Focus,
  Minus,
  Network,
  Plus,
  Target,
} from "lucide-react";
import { buildMindMap, fitMindMap, zoomMindMap } from "./mindMapLayout";

const labels = { unknown: "待诊断", learning: "学习中", mastered: "已掌握" };
const colors = ["#6c8a65", "#bc9464", "#788fa4", "#a7848e", "#8a85ac"];

function connection(from, to, laneY) {
  const direction = Math.sign(to.x - from.x) || 1;
  const x1 = from.x + (direction * from.width) / 2;
  const x2 = to.x - (direction * to.width) / 2;
  if (laneY !== undefined) {
    const a = x1 + direction * 28,
      b = x2 - direction * 28;
    return `M ${x1} ${from.y} C ${a} ${from.y}, ${a} ${laneY}, ${a} ${laneY} L ${b} ${laneY} C ${b} ${laneY}, ${b} ${to.y}, ${x2} ${to.y}`;
  }
  const bend = Math.max(48, Math.abs(x2 - x1) * 0.48);
  return `M ${x1} ${from.y} C ${x1 + direction * bend} ${from.y}, ${x2 - direction * bend} ${to.y}, ${x2} ${to.y}`;
}

export default function KnowledgeMindMap({ concepts, states, goal }) {
  const map = useMemo(() => buildMindMap(concepts), [concepts]);
  const byKey = useMemo(() => new Map(map.nodes.map((n) => [n.key, n])), [map]);
  const profiles = useMemo(
    () => new Map(states.map((s) => [s.concept_id, s])),
    [states],
  );
  const canvas = useRef(null);
  const nodeButtons = useRef(new Map());
  const gesture = useRef({ pointers: new Map(), moved: false, distance: 0 });
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [selected, setSelected] = useState(null);
  const arrowId = useId().replaceAll(":", "");
  const current = byKey.get(selected);
  const profile = profiles.get(selected);
  const root = { x: 0, y: 0, width: 244, height: 112 };
  const status = (key) =>
    labels[profiles.get(key)?.status] ? profiles.get(key).status : "unknown";

  function fit() {
    const element = canvas.current;
    if (element)
      setView(
        fitMindMap(map.bounds, element.clientWidth, element.clientHeight),
      );
  }
  useLayoutEffect(() => {
    const element = canvas.current;
    const observer = new ResizeObserver(() => {
      setView(
        fitMindMap(map.bounds, element.clientWidth, element.clientHeight),
      );
    });
    observer.observe(element);
    setView(fitMindMap(map.bounds, element.clientWidth, element.clientHeight));
    return () => observer.disconnect();
  }, [map]);
  useEffect(() => {
    const element = canvas.current;
    const wheel = (event) => {
      event.preventDefault();
      const box = element.getBoundingClientRect();
      setView((old) =>
        zoomMindMap(
          old,
          Math.exp(-event.deltaY * (event.ctrlKey ? 0.01 : 0.002)),
          { x: event.clientX - box.left, y: event.clientY - box.top },
        ),
      );
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, []);

  function zoom(factor) {
    const element = canvas.current;
    setView((old) =>
      zoomMindMap(old, factor, {
        x: element.clientWidth / 2,
        y: element.clientHeight / 2,
      }),
    );
  }
  function focusNode(node) {
    setSelected(node.key);
    const element = canvas.current;
    setView((old) => ({
      ...old,
      scale: Math.max(old.scale, 0.85),
      x: element.clientWidth / 2 - node.x * Math.max(old.scale, 0.85),
      y: element.clientHeight / 2 - node.y * Math.max(old.scale, 0.85),
    }));
    nodeButtons.current.get(node.key)?.focus({ preventScroll: true });
  }
  function start(event) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const state = gesture.current;
    if (!state.pointers.size) {
      state.moved = false;
      state.distance = 0;
    }
    state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const target = event.target.closest("button") || canvas.current;
    target.setPointerCapture(event.pointerId);
  }
  function move(event) {
    const state = gesture.current;
    const previous = state.pointers.get(event.pointerId);
    if (!previous) return;
    const before = [...state.pointers.values()];
    const point = { x: event.clientX, y: event.clientY };
    state.pointers.set(event.pointerId, point);
    const after = [...state.pointers.values()];
    state.distance += Math.hypot(point.x - previous.x, point.y - previous.y);
    if (state.distance > 5) state.moved = true;
    if (after.length === 1) {
      setView((old) => ({
        ...old,
        x: old.x + point.x - previous.x,
        y: old.y + point.y - previous.y,
      }));
    } else if (after.length === 2) {
      const midpoint = (points) => ({
        x: (points[0].x + points[1].x) / 2,
        y: (points[0].y + points[1].y) / 2,
      });
      const distance = (points) =>
        Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
      const a = midpoint(before),
        b = midpoint(after),
        box = canvas.current.getBoundingClientRect();
      state.moved = true;
      setView((old) =>
        zoomMindMap(
          { ...old, x: old.x + b.x - a.x, y: old.y + b.y - a.y },
          distance(after) / Math.max(1, distance(before)),
          { x: b.x - box.left, y: b.y - box.top },
        ),
      );
    }
  }
  function end(event) {
    gesture.current.pointers.delete(event.pointerId);
  }
  function keyboard(event) {
    if (event.target !== event.currentTarget) return;
    const offsets = {
      ArrowLeft: [60, 0],
      ArrowRight: [-60, 0],
      ArrowUp: [0, 60],
      ArrowDown: [0, -60],
    };
    if (offsets[event.key]) {
      event.preventDefault();
      const [x, y] = offsets[event.key];
      setView((old) => ({ ...old, x: old.x + x, y: old.y + y }));
    } else if (["+", "=", "-", "0"].includes(event.key)) {
      event.preventDefault();
      if (event.key === "0") fit();
      else zoom(event.key === "-" ? 0.8 : 1.25);
    }
  }

  return (
    <div className="mind-map-layout">
      <section className="card mind-map-card" aria-label="知识脑图">
        <div className="mind-map-heading">
          <div>
            <span className="mind-map-eyebrow">围绕目标梳理知识结构</span>
            <h3>
              <Network size={18} /> 从目标，看见知识的联系
            </h3>
          </div>
          <span className="mind-map-count">{concepts.length} 个知识点</span>
        </div>
        <div className="mind-map-toolbar">
          <div className="mind-map-legend" aria-label="掌握状态图例">
            {Object.entries(labels).map(([key, label]) => (
              <span key={key} className={key}>
                <i />
                {label}
              </span>
            ))}
          </div>
          <select
            className="mind-map-jump"
            aria-label="定位知识点"
            value={current?.key || ""}
            onChange={(event) => focusNode(byKey.get(event.target.value))}
          >
            <option value="" disabled>
              定位知识点…
            </option>
            {map.nodes.map((node) => (
              <option key={node.key} value={node.key}>
                {node.name}
              </option>
            ))}
          </select>
          <div
            className="mind-map-controls"
            role="group"
            aria-label="脑图视图操作"
          >
            <button
              aria-label="缩小脑图"
              onClick={() => zoom(0.8)}
              disabled={view.scale <= 0.01}
            >
              <Minus size={16} />
            </button>
            <span aria-live="polite">{Math.round(view.scale * 100)}%</span>
            <button
              aria-label="放大脑图"
              onClick={() => zoom(1.25)}
              disabled={view.scale >= 2.5}
            >
              <Plus size={16} />
            </button>
            <button
              aria-label="居中适配脑图"
              title="居中适配（0）"
              onClick={fit}
            >
              <Focus size={16} />
            </button>
          </div>
        </div>
        <div
          ref={canvas}
          className="mind-map-canvas"
          tabIndex={0}
          role="group"
          aria-label="可拖动和缩放的知识脑图"
          aria-describedby="mind-map-help"
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={end}
          onPointerCancel={end}
          onLostPointerCapture={end}
          onKeyDown={keyboard}
        >
          <div
            className="mind-map-world"
            style={{
              transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
            }}
          >
            <svg
              className="mind-map-links"
              aria-hidden="true"
              width="1"
              height="1"
            >
              <defs>
                <marker
                  id={arrowId}
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#a6ada0" />
                </marker>
              </defs>
              {map.edges.map((edge, index) => {
                const to = byKey.get(edge.to),
                  from = edge.from === null ? root : byKey.get(edge.from);
                const related =
                  selected && (edge.from === selected || edge.to === selected);
                return (
                  <path
                    key={index}
                    d={connection(from, to, edge.laneY)}
                    className={`mind-map-link${edge.secondary ? " secondary" : ""}${related ? " related" : ""}`}
                    style={{ stroke: colors[to.branch % colors.length] }}
                    markerEnd={edge.secondary ? `url(#${arrowId})` : undefined}
                  />
                );
              })}
            </svg>
            <button
              className="mind-map-root"
              style={{ left: -122, top: -56 }}
              onClick={(event) => {
                if (event.detail === 0 || !gesture.current.moved)
                  setSelected(null);
              }}
              aria-label={`学习目标：${goal}`}
            >
              <span>
                <Target size={14} /> 学习目标
              </span>
              <strong title={goal}>{goal}</strong>
              <small>
                {concepts.length
                  ? "分支展示知识结构与前置关系"
                  : "课程知识点生成后将在这里展开"}
              </small>
            </button>
            {map.nodes.map((node) => (
              <button
                key={node.key}
                ref={(element) => {
                  if (element) nodeButtons.current.set(node.key, element);
                  else nodeButtons.current.delete(node.key);
                }}
                className={`mind-map-node ${status(node.key)}${selected === node.key ? " selected" : ""}`}
                style={{
                  left: node.x - node.width / 2,
                  top: node.y - node.height / 2,
                  width: node.width,
                  height: node.height,
                  "--branch-color": colors[node.branch % colors.length],
                }}
                title={node.name}
                aria-label={`${node.name}，${labels[status(node.key)]}`}
                aria-pressed={selected === node.key}
                onFocus={(event) => {
                  const box = event.currentTarget.getBoundingClientRect(),
                    area = canvas.current.getBoundingClientRect();
                  if (
                    box.left < area.left ||
                    box.right > area.right ||
                    box.top < area.top ||
                    box.bottom > area.bottom
                  )
                    focusNode(node);
                }}
                onClick={(event) => {
                  if (event.detail === 0 || !gesture.current.moved)
                    setSelected(node.key);
                }}
              >
                <span className="mind-map-module">{node.module}</span>
                <strong>{node.name}</strong>
                <span className={`mind-map-node-status ${status(node.key)}`}>
                  <i />
                  {labels[status(node.key)]}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="mind-map-caption" id="mind-map-help">
          <span>拖动平移 · 滚轮 / 双指缩放 · 点击节点查看</span>
          <span>
            <i /> 实线：主分支 <i className="dashed" /> 虚线：其他前置关联
          </span>
        </div>
      </section>
      <aside
        className="card mind-map-detail"
        aria-label="知识点详情"
        aria-live="polite"
      >
        {current ? (
          <>
            <span className="mind-map-eyebrow">查看知识点与学习依据</span>
            <span className={`status ${status(selected)}`}>
              {labels[status(selected)]}
            </span>
            <h3>{current.name}</h3>
            <p className="mind-map-detail-module">
              {current.module} · 建议 {current.minutes} 分钟
            </p>
            <div className="mind-map-evidence">
              <strong>
                {profile?.evidence_count || 0}
                <small> 条有效证据</small>
              </strong>
              <p>掌握状态来自独立作答与学习证据。</p>
            </div>
            <h4>
              <BookOpen size={15} /> 学习目标
            </h4>
            <ul>
              {current.objectives?.map((objective, i) => (
                <li key={i}>{objective}</li>
              ))}
            </ul>
            <h4>前置知识</h4>
            {current.prerequisites?.length ? (
              <div className="mind-map-relations">
                {current.prerequisites.map((key) => (
                  <button
                    key={key}
                    disabled={!byKey.has(key)}
                    onClick={() => focusNode(byKey.get(key))}
                  >
                    {byKey.get(key)?.name || key}
                    <ArrowRight size={13} />
                  </button>
                ))}
              </div>
            ) : (
              <p className="small muted">基础知识点，无需其他前置知识。</p>
            )}
            {map.nodes.some((n) => n.prerequisites?.includes(selected)) && (
              <>
                <h4>继续拓展</h4>
                <div className="mind-map-relations">
                  {map.nodes
                    .filter((n) => n.prerequisites?.includes(selected))
                    .map((n) => (
                      <button key={n.key} onClick={() => focusNode(n)}>
                        {n.name}
                        <ArrowRight size={13} />
                      </button>
                    ))}
                </div>
              </>
            )}
            <p className="mind-map-source">
              课程结构由模型生成，请结合教材核对。待诊断表示尚无足够作答记录。
            </p>
          </>
        ) : (
          <div className="mind-map-detail-empty">
            <span className="icon-box">
              <Network size={24} />
            </span>
            <span className="mind-map-eyebrow">点击知识点，了解学习路径</span>
            <h3>
              每个知识点，
              <br />
              都有它的位置。
            </h3>
            <p>点击脑图中的知识点，查看学习目标、前置关系和已有证据。</p>
            <div className="mind-map-detail-note">
              <Target size={17} />
              <span>中心是你的目标，分支串起学习路径。</span>
            </div>
            <p className="mind-map-source">
              关系表示学习前置条件，不代表已经掌握。
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}
