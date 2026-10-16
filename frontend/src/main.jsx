import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  Cpu,
  FlaskConical,
  Layers,
  LoaderCircle,
  LogOut,
  Network,
  Plus,
  Settings2,
  ShieldCheck,
  Sparkles,
  Target,
  History,
} from "lucide-react";
import { api, key } from "./api";
import { createLatestRequest } from "./latestRequest";
import "./styles.css";
import Materials, { Citations } from "./Materials";

const labels = { unknown: "待诊断", learning: "学习中", mastered: "已掌握" };
const actions = {
  DIAGNOSE: "初始诊断",
  LEARN_CONCEPT: "学习新知",
  REMEDIATE: "修复误区",
  PRACTICE: "定向练习",
  ASSESS: "迁移测评",
};
const eventLabels = {
  diagnostic_submitted: "完成诊断",
  assessment_submitted: "提交练习",
  lesson_viewed: "阅读讲解",
  hint_requested: "请求提示",
  plan_adjusted: "调整学习计划",
};

function App() {
  const [user, setUser] = useState(null),
    [ready, setReady] = useState(false);
  const [config, setConfig] = useState({}),
    [spaces, setSpaces] = useState([]),
    [providers, setProviders] = useState([]);
  const [sid, setSid] = useState(""),
    [page, setPage] = useState("overview"),
    [modal, setModal] = useState("");
  const [detail, setDetail] = useState(null),
    [diagnosis, setDiagnosis] = useState(null),
    [lesson, setLesson] = useState(null);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const spaceReads = useRef(createLatestRequest()),
    listReads = useRef(createLatestRequest());
  const activeSpace = useRef(sid),
    sessionScope = useRef(createLatestRequest()),
    operation = useRef(0);
  activeSpace.current = sid;
  function selectSpace(id) {
    if (activeSpace.current !== id) spaceReads.current.invalidate();
    activeSpace.current = id;
    setSid(id);
  }
  function invalidateSession() {
    sessionScope.current.invalidate();
    spaceReads.current.invalidate();
    listReads.current.invalidate();
    selectSpace("");
    setSpaces([]);
    setProviders([]);
    setDetail(null);
    setDiagnosis(null);
    setLesson(null);
    setModal("");
    setPage("overview");
  }
  const space = spaces.find((s) => s.id === sid);
  async function refreshLists() {
    await listReads.current.run(
      () => Promise.all([api("/study-spaces"), api("/providers")]),
      ([s, p]) => {
        setSpaces(s);
        setProviders(p);
        selectSpace(
          s.some((x) => x.id === activeSpace.current)
            ? activeSpace.current
            : s[0]?.id || "",
        );
      },
    );
  }
  async function refreshSpace(id = sid) {
    if (!id || id !== activeSpace.current) return;
    const root = "/study-spaces/" + id;
    await spaceReads.current.run(
      () =>
        Promise.all([
          api(root + "/concepts"),
          api(root + "/profile"),
          api(root + "/next-action"),
          api(root + "/events"),
          api(root + "/runs"),
          api(root + "/plan"),
          api(root + "/lessons/current"),
        ]),
      ([concepts, profile, action, events, runs, plan, current]) => {
        if (id !== activeSpace.current) return;
        setDetail({ concepts, profile, action, events, runs, plan });
        setLesson(current);
      },
    );
  }
  async function work(message, fn) {
    const ticket = ++operation.current,
      isCurrent = sessionScope.current.checkpoint();
    setError("");
    setBusy(message);
    try {
      return await fn(isCurrent);
    } catch (e) {
      if (ticket === operation.current && isCurrent()) setError(e.message);
    } finally {
      if (ticket === operation.current) setBusy("");
    }
  }
  useEffect(() => {
    api("/config")
      .then(setConfig)
      .catch(() => {});
    api("/auth/me")
      .then(async (u) => {
        setUser(u);
        await refreshLists();
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    setDiagnosis(null);
    setDetail(null);
    setLesson(null);
    if (sid) work("读取学习进度", () => refreshSpace(sid));
  }, [sid]);
  const root = "/study-spaces/" + sid;
  const stats = detail?.profile.states || [];
  const mastered = stats.filter((s) => s.status === "mastered").length;
  const currentProvider = providers.find((p) => p.id === space?.provider_id);
  async function beginDiagnosis() {
    const isCurrent = sessionScope.current.checkpoint(),
      id = sid;
    await work("生成诊断题", async () => {
      const result = await api(root + "/diagnostics", { method: "POST" });
      if (!isCurrent() || id !== activeSpace.current) return;
      setDiagnosis(result);
      setPage("classroom");
    });
  }
  async function beginLesson() {
    const isCurrent = sessionScope.current.checkpoint(),
      id = sid;
    await work("为你准备课堂", async () => {
      const result = await api(root + "/lessons", {
        method: "POST",
        body: { idempotency_key: key() },
      });
      if (!isCurrent() || id !== activeSpace.current) return;
      setLesson(result);
      setDiagnosis(null);
      setPage("classroom");
    });
  }
  async function answered(item, answer, requestKey) {
    const isCurrent = sessionScope.current.checkpoint(),
      id = sid;
    const result = await api(root + "/attempts", {
      method: "POST",
      body: { item_id: item.id, answer, idempotency_key: requestKey },
    });
    if (!isCurrent() || id !== activeSpace.current) return result;
    if (diagnosis)
      setDiagnosis((old) => ({
        ...old,
        attempts: { ...old?.attempts, [item.id]: result },
      }));
    await refreshSpace();
    return result;
  }
  if (!ready)
    return (
      <div className="loading">
        <LoaderCircle className="spin" /> 正在连接学习空间
      </div>
    );
  if (!user)
    return (
      <Auth
        onLogin={async (u) => {
          invalidateSession();
          setUser(u);
          await refreshLists();
        }}
        config={config}
      />
    );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("overview");
          }}
        >
          <span className="brand-icon">
            <Layers size={22} />
          </span>{" "}
          StudyAgent<span className="brand-dot">®</span>
        </a>
        <div className="workspace-label">PERSONAL LEARNING SPACE</div>
        <select
          className="space-select"
          aria-label="选择学习空间"
          value={sid}
          onChange={(e) => {
            selectSpace(e.target.value);
            setPage("overview");
          }}
        >
          <option value="" disabled>
            创建你的学习空间
          </option>
          {spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.goal}
            </option>
          ))}
        </select>
        <button className="new-space" onClick={() => setModal("space")}>
          <Plus size={15} /> 新建学习空间
        </button>
        <div className="nav-label">你的学习</div>
        <nav>
          {[
            ["overview", BookOpen, "学习概览"],
            ["classroom", Sparkles, "专属课堂"],
            ["knowledge", Network, "知识地图"],
            ["materials", Layers, "私人教材"],
            ["history", History, "学习记录"],
            ["settings", Settings2, "模型与设置"],
          ].map(([id, Icon, title]) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => setPage(id)}
            >
              <Icon size={18} />
              {title}
              {id === "classroom" && <span className="tiny-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <ShieldCheck size={17} />
            <span>
              你的模型，你的学习数据
              <br />
              <small>BYOK · 独立空间 · 证据可追溯</small>
            </span>
          </div>
          <div className="user">
            <span className="avatar">{user.username[0].toUpperCase()}</span>
            <span>
              {user.username}
              <small>个人学习者</small>
            </span>
            <button
              title="退出登录"
              onClick={() =>
                work("退出登录", async (isCurrent) => {
                  await api("/auth/logout", { method: "POST" });
                  if (!isCurrent()) return;
                  setUser(null);
                  invalidateSession();
                  setSpaces([]);
                  setDetail(null);
                })
              }
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <span>
            学习工作台 <ChevronRight size={13} />{" "}
            <b>
              {
                {
                  overview: "学习概览",
                  classroom: "专属课堂",
                  knowledge: "知识地图",
                  materials: "私人教材",
                  history: "学习记录",
                  settings: "模型与设置",
                }[page]
              }
            </b>
          </span>
          <span className="phase">
            <span /> M2 · 私人教材
          </span>
        </header>
        <div className="main-content">
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => setError("")}>×</button>
            </div>
          )}
          {busy && (
            <div className="busy" role="status">
              <LoaderCircle size={16} className="spin" />
              {busy}… 模型任务可能需要一点时间
            </div>
          )}
          {page === "settings" ? (
            <>
              <PageTitle
                eyebrow="CONNECTED INTELLIGENCE"
                title="模型与设置"
                subtitle="连接你信任的模型，学习进度由框架持续保存。"
              />
              <div className="section-head">
                <h3>我的模型连接</h3>
                <button
                  className="primary"
                  onClick={() => setModal("provider")}
                >
                  <Plus size={16} /> 添加模型
                </button>
              </div>
              <div className="provider-grid">
                {providers.map((p) => (
                  <article className="card provider-card" key={p.id}>
                    <Cpu />
                    <span className={"tag " + (p.tested ? "green" : "")}>
                      {p.tested ? "已检测" : "待检测"}
                    </span>
                    <h3>{p.name}</h3>
                    <p>{p.chat_model}</p>
                    <code>{p.base_url}</code>
                    <div className="cap-list">
                      <span>聊天 {p.capabilities.chat ? "✓" : "待验证"}</span>
                      <span>
                        文件理解：
                        {p.capabilities.file_input
                          ? p.capabilities.supported_mime_types?.join("、")
                          : "未验证或不支持"}
                      </span>
                      <span>
                        远端 Embedding：
                        {p.capabilities.embedding ? "已验证" : "未验证或不支持"}
                      </span>
                      {p.capabilities.is_demo && (
                        <span>固定演示 · 未读取文件内容</span>
                      )}
                      {p.capabilities.file_error && (
                        <span>文件检测：{p.capabilities.file_error}</span>
                      )}
                      {p.capabilities.retention_warning && (
                        <span>{p.capabilities.retention_warning}</span>
                      )}
                    </div>
                    <div className="button-row">
                      <button
                        onClick={() =>
                          work("检测模型能力", async (isCurrent) => {
                            await api("/providers/" + p.id + "/test", {
                              method: "POST",
                            });
                            if (!isCurrent()) return;
                            await refreshLists();
                          })
                        }
                        disabled={!!busy}
                      >
                        测试连接
                      </button>
                      <button onClick={() => setModal(p)}>编辑凭证</button>
                      <button
                        className="danger"
                        onClick={() =>
                          work("删除模型配置", async (isCurrent) => {
                            await api("/providers/" + p.id, {
                              method: "DELETE",
                            });
                            if (!isCurrent()) return;
                            await refreshLists();
                          })
                        }
                      >
                        删除
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              {space && (
                <section className="card model-switch">
                  <h3>当前学习空间的教学模型</h3>
                  <p className="small muted">
                    切换模型后，知识状态、学习计划和历史证据继续保留。
                  </p>
                  <select
                    aria-label="切换教学模型"
                    value={space.provider_id}
                    disabled={!!busy}
                    onChange={(e) =>
                      work("切换教学模型", async (isCurrent) => {
                        await api(root, {
                          method: "PATCH",
                          body: { provider_id: e.target.value },
                        });
                        if (!isCurrent()) return;
                        await refreshLists();
                        if (!isCurrent()) return;
                        await refreshSpace();
                      })
                    }
                  >
                    {providers
                      .filter((p) => p.tested || p.id === space.provider_id)
                      .map((p) => (
                        <option key={p.id} value={p.id} disabled={!p.tested}>
                          {p.name} · {p.chat_model}
                          {!p.tested ? "（需要重新检测）" : ""}
                        </option>
                      ))}
                  </select>
                  {currentProvider?.provider_type === "fake" && (
                    <p className="hint">
                      当前为离线演示，使用固定操作系统样例。
                    </p>
                  )}
                </section>
              )}
              <p className="muted small">
                API Key
                只在后端加密保存。连接测试与教学会向你选择的服务发送请求并可能产生费用。令牌用量见学习记录，金额以服务商账单为准。
              </p>
            </>
          ) : !space ? (
            <div className="empty-space">
              <span className="eyebrow">YOUR NEXT CHAPTER</span>
              <h1>从一个想学的目标开始。</h1>
              <p>连接自己的模型，让每一步学习都有依据。</p>
              <div className="button-row">
                <button onClick={() => setModal("provider")}>
                  1. 连接模型 <ArrowUpRight size={16} />
                </button>
                <button className="primary" onClick={() => setModal("space")}>
                  2. 创建学习空间 <ArrowRight size={16} />
                </button>
              </div>
              <div className="empty-graphic">
                <Layers size={100} strokeWidth={0.7} />
                <span>GOAL → EVIDENCE → GROWTH</span>
              </div>
            </div>
          ) : !detail ? (
            <div className="loading">
              <LoaderCircle className="spin" /> 正在读取进度
            </div>
          ) : (
            <>
              {page === "materials" && (
                <Materials
                  key={user.id + sid}
                  root={root}
                  space={space}
                  provider={currentProvider}
                  maxBytes={config.material_max_bytes}
                  onRefresh={async () => {
                    await refreshLists();
                    await refreshSpace();
                  }}
                />
              )}
              {page === "overview" && (
                <>
                  <PageTitle
                    eyebrow="A LITTLE PROGRESS, EVERY DAY"
                    title="让学习，循序向前。"
                    subtitle="不止记录你学过什么，更关心你真正掌握了什么。"
                  />
                  <div className="hero-grid">
                    <section className="hero">
                      <div className="hero-top">
                        <span className="tag pale">正在学习</span>
                        <span className="hero-index">
                          LEARNING JOURNEY /{" "}
                          {String(spaces.indexOf(space) + 1).padStart(2, "0")}
                        </span>
                      </div>
                      <h2>{space.goal}</h2>
                      <p>
                        每天 {space.daily_minutes} 分钟 · {space.expected_level}
                        {space.target_date
                          ? " · 目标 " + space.target_date
                          : ""}
                      </p>
                      <div className="hero-bottom">
                        <div>
                          <span className="hero-progress">
                            {mastered}
                            <small> / {stats.length}</small>
                          </span>
                          <span className="hero-progress-caption">
                            知识点达到初步掌握
                          </span>
                        </div>
                        <button
                          className="light-button"
                          disabled={!!busy}
                          onClick={
                            detail.events.some(
                              (e) => e.type === "diagnostic_submitted",
                            )
                              ? beginLesson
                              : beginDiagnosis
                          }
                        >
                          继续我的学习 <ArrowUpRight size={18} />
                        </button>
                      </div>
                      <div className="hero-decoration">
                        <div />
                        <div />
                        <div />
                      </div>
                    </section>
                    <section className="card next-card">
                      <div className="eyebrow">
                        <span className="orange-dot" /> NEXT BEST STEP
                      </div>
                      <h3>{actions[detail.action.action]}</h3>
                      <strong>
                        {
                          detail.concepts.find(
                            (c) => c.key === detail.action.concept_ids[0],
                          )?.name
                        }
                      </strong>
                      <p>{detail.action.reason}</p>
                      <div className="next-foot">
                        <span>约 {detail.action.estimated_minutes} 分钟</span>
                        <span>
                          {detail.action.evidence_event_ids.length} 条依据
                        </span>
                      </div>
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={
                          detail.action.action === "DIAGNOSE"
                            ? beginDiagnosis
                            : beginLesson
                        }
                      >
                        开始这一步 <ArrowRight size={17} />
                      </button>
                    </section>
                  </div>
                  <div className="metrics">
                    <Metric
                      label="课程知识点"
                      value={stats.length}
                      unit="个"
                      detail="候选课程 · 模型生成"
                      icon={Network}
                    />
                    <Metric
                      label="已获得学习证据"
                      value={
                        detail.events.filter((e) =>
                          [
                            "assessment_submitted",
                            "diagnostic_submitted",
                          ].includes(e.type),
                        ).length
                      }
                      unit="次"
                      detail="每次作答均可回溯"
                      icon={Target}
                    />
                    <Metric
                      label="今日学习预算"
                      value={space.daily_minutes}
                      unit="分钟"
                      detail="按你的可用时间安排"
                      icon={BookOpen}
                    />
                  </div>
                  <div className="lower-grid">
                    <section className="card">
                      <div className="section-head">
                        <h3>知识掌握概览</h3>
                        <button
                          className="text-button"
                          onClick={() => setPage("knowledge")}
                        >
                          查看全部 <ArrowUpRight size={15} />
                        </button>
                      </div>
                      {detail.concepts.map((c, i) => (
                        <ConceptRow
                          key={c.key}
                          concept={c}
                          state={stats.find((s) => s.concept_id === c.key)}
                          index={i}
                        />
                      ))}
                    </section>
                    <section className="card principles">
                      <span className="icon-box">
                        <FlaskConical size={22} />
                      </span>
                      <h3>每一份进步，都有依据。</h3>
                      <p>
                        阅读只代表学习经历。通过不同题目的独立作答，才能逐步建立可靠的掌握证据。
                      </p>
                      <div>
                        <Check size={15} /> 状态持久保存，可跨会话继续
                      </div>
                      <div>
                        <Check size={15} /> 下一步推荐有可查看的理由
                      </div>
                      <div>
                        <Check size={15} /> 未验证的知识明确标注
                      </div>
                    </section>
                  </div>
                </>
              )}
              {page === "knowledge" && (
                <>
                  <PageTitle
                    eyebrow="KNOW WHAT YOU KNOW"
                    title="你的知识地图"
                    subtitle="先打好基础，再迈向下一层。未知状态表示证据不足。"
                  />
                  <div className="card">
                    {detail.concepts.map((c, i) => (
                      <div className="concept-expanded" key={c.key}>
                        <ConceptRow
                          concept={c}
                          state={stats.find((s) => s.concept_id === c.key)}
                          index={i}
                        />
                        <p>{c.objectives.join(" · ")}</p>
                        <p className="small muted">
                          前置知识：
                          {c.prerequisites
                            .map(
                              (k) =>
                                detail.concepts.find((x) => x.key === k)?.name,
                            )
                            .join("、") || "无"}{" "}
                          · 来源：模型生成、待核实
                        </p>
                      </div>
                    ))}
                  </div>
                </>
              )}
              {page === "classroom" && (
                <>
                  <PageTitle
                    eyebrow="ONE CONCEPT AT A TIME"
                    title="专属课堂"
                    subtitle="带着问题学习，用真实表现积累证据。"
                  />
                  <div className="button-row classroom-tabs">
                    <button onClick={beginDiagnosis} disabled={!!busy}>
                      初始诊断
                    </button>
                    <button
                      className="primary"
                      onClick={beginLesson}
                      disabled={!!busy}
                    >
                      开始 / 继续课堂 <Sparkles size={15} />
                    </button>
                  </div>
                  {diagnosis ? (
                    <section className="card lesson">
                      <span className="tag">
                        初始诊断 · {diagnosis.items.length} 题
                      </span>
                      <h2>先了解你的起点</h2>
                      <p className="muted">{diagnosis.notice}</p>
                      {diagnosis.items.map((item, i) => (
                        <Question
                          key={item.id}
                          item={item}
                          index={i}
                          initial={diagnosis.attempts?.[item.id]}
                          onAnswer={answered}
                          onHint={async (id) =>
                            (
                              await api(root + "/items/" + id + "/hint", {
                                method: "POST",
                                body: { idempotency_key: key() },
                              })
                            ).hint
                          }
                        />
                      ))}
                      <button
                        className="primary"
                        onClick={async () => {
                          setDiagnosis(null);
                          await beginLesson();
                        }}
                      >
                        进入课堂 <ArrowRight size={16} />
                      </button>
                    </section>
                  ) : lesson ? (
                    <section className="card lesson">
                      <span className="tag green">
                        {actions[lesson.action.action]} · 模型生成，待核实
                      </span>
                      <h2>{lesson.title}</h2>
                      <div className="prose">{lesson.explanation}</div>
                      <Citations sources={lesson.citations} root={root} />
                      <div className="example">
                        <b>一个具体的例子</b>
                        <p>{lesson.example}</p>
                      </div>
                      <button
                        disabled={!!busy || lesson.completed}
                        onClick={() =>
                          work("记录阅读经历", async (isCurrent) => {
                            await api(
                              root + "/lessons/" + lesson.id + "/complete",
                              {
                                method: "POST",
                                body: { idempotency_key: key() },
                              },
                            );
                            if (!isCurrent()) return;
                            await refreshSpace();
                          })
                        }
                      >
                        {lesson.completed ? "已记录阅读经历" : "我已阅读讲解"}{" "}
                        <Check size={15} />
                      </button>
                      <h3>动手验证一下</h3>
                      {lesson.exercises.map((item, i) => (
                        <Question
                          key={item.id}
                          item={item}
                          index={i}
                          initial={lesson.attempts?.[item.id]}
                          onAnswer={answered}
                          onHint={async (id) =>
                            (
                              await api(root + "/items/" + id + "/hint", {
                                method: "POST",
                                body: { idempotency_key: key() },
                              })
                            ).hint
                          }
                        />
                      ))}
                      <button
                        className="primary"
                        disabled={!!busy}
                        onClick={beginLesson}
                      >
                        下一次学习 <ArrowRight size={16} />
                      </button>
                    </section>
                  ) : (
                    <div className="card empty-class">
                      <BookOpen size={36} />
                      <h3>为今天的学习，迈出第一步。</h3>
                      <p>先完成诊断，或按推荐开始一节专属课堂。</p>
                    </div>
                  )}
                </>
              )}
              {page === "history" && (
                <>
                  <PageTitle
                    eyebrow="EVIDENCE OF YOUR PROGRESS"
                    title="每一步，都留下记录"
                    subtitle="学习事件只追加保存。模型调用用量与学习决策均可追溯。"
                  />
                  <section className="card">
                    <h3>学习时间线</h3>
                    {detail.events.length === 0 && (
                      <p className="muted">
                        还没有学习记录，完成一次诊断开始积累证据。
                      </p>
                    )}
                    {[...detail.events].reverse().map((e) => (
                      <div className="timeline-row" key={e.event_id}>
                        <span className="timeline-dot" />
                        <div>
                          <b>{eventLabels[e.type] || e.type}</b>
                          <p>
                            {e.payload.is_correct === true
                              ? "回答正确"
                              : e.payload.is_correct === false
                                ? "尚未答对"
                                : e.payload.next_action?.reason ||
                                  "学习经历已保存"}
                            {e.payload.assistance_level === "hint"
                              ? " · 使用了提示"
                              : ""}
                          </p>
                          <code>{e.event_id.slice(0, 8)}</code>
                        </div>
                        <time>
                          {new Date(
                            e.occurred_at.endsWith("Z") ||
                              /[+-]\d\d:\d\d$/.test(e.occurred_at)
                              ? e.occurred_at
                              : e.occurred_at + "Z",
                          ).toLocaleString("zh-CN")}
                        </time>
                      </div>
                    ))}
                  </section>
                  <section className="card runs">
                    <h3>模型调用记录</h3>
                    {detail.runs.map((r) => (
                      <div className="run-row" key={r.run_id}>
                        <span>{r.step}</span>
                        <code>{r.model}</code>
                        <span>{r.elapsed_ms} ms</span>
                        <span>
                          {(r.usage.prompt_tokens || 0) +
                            (r.usage.completion_tokens || 0)}{" "}
                          tokens
                        </span>
                        <span>
                          {r.error_code ||
                            (r.usage.cost_status === "demo_no_charge"
                              ? "离线演示 · 无费用"
                              : "金额未提供")}
                        </span>
                      </div>
                    ))}
                  </section>
                </>
              )}
            </>
          )}
          <footer>
            <span>StudyAgent Framework</span>
            <span>以目标为起点，以证据为方向。</span>
            <span>BYOK / M2</span>
          </footer>
        </div>
      </main>
      {modal && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={modal === "space" ? "创建学习空间" : "模型配置"}
          >
            <button
              className="modal-close"
              aria-label="关闭"
              onClick={() => setModal("")}
            >
              ×
            </button>
            {modal === "space" ? (
              <SpaceForm
                providers={providers}
                busy={busy}
                onSubmit={(body) =>
                  work("构建候选课程", async (isCurrent) => {
                    const s = await api("/study-spaces", {
                      method: "POST",
                      body,
                    });
                    if (!isCurrent()) return;
                    await refreshLists();
                    if (!isCurrent()) return;
                    selectSpace(s.id);
                    setPage("overview");
                    setModal("");
                  })
                }
              />
            ) : (
              <ProviderForm
                existing={typeof modal === "object" ? modal : null}
                demo={config.demo_enabled}
                busy={busy}
                onSubmit={(body) =>
                  work("保存模型连接", async (isCurrent) => {
                    const editing = typeof modal === "object";
                    await api("/providers" + (editing ? "/" + modal.id : ""), {
                      method: editing ? "PATCH" : "POST",
                      body,
                    });
                    if (!isCurrent()) return;
                    await refreshLists();
                    if (!isCurrent()) return;
                    setModal("");
                    setPage("settings");
                  })
                }
              />
            )}{" "}
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function PageTitle({ eyebrow, title, subtitle }) {
  return (
    <div className="page-title">
      <span className="eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
  );
}
function Metric({ label, value, unit, detail, icon: Icon }) {
  return (
    <section className="metric">
      <div>
        <span>{label}</span>
        <Icon size={18} />
      </div>
      <strong>
        {value}
        <small>{unit}</small>
      </strong>
      <p>{detail}</p>
    </section>
  );
}
function ConceptRow({ concept, state, index }) {
  return (
    <div className="concept-row">
      <span className="concept-number">
        {String(index + 1).padStart(2, "0")}
      </span>
      <div className="concept-info">
        <b>{concept.name}</b>
        <small>
          {concept.module} · {state?.evidence_count || 0} 条有效证据
        </small>
      </div>
      <span className={"status " + (state?.status || "unknown")}>
        {labels[state?.status || "unknown"]}
      </span>
    </div>
  );
}

function Question({ item, index, initial, onAnswer, onHint }) {
  const [answer, setAnswer] = useState(""),
    [result, setResult] = useState(initial),
    [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [requestKey] = useState(key);
  useEffect(() => {
    if (initial) setResult(initial);
  }, [initial]);
  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="question">
      <div className="question-heading">
        <span>练习 {String(index + 1).padStart(2, "0")}</span>
        <small>难度 {item.difficulty} / 5</small>
      </div>
      <h4>{item.prompt}</h4>
      <Citations sources={item.citations} />
      {item.kind === "choice" ? (
        <div className="options">
          {Object.entries(item.options).map(([k, text]) => (
            <label key={k} className={answer === k ? "selected" : ""}>
              <input
                type="radio"
                name={item.id}
                value={k}
                checked={answer === k}
                disabled={busy || !!result}
                onChange={() => setAnswer(k)}
              />
              <b>{k}</b>
              {text}
            </label>
          ))}
        </div>
      ) : (
        <textarea
          aria-label="你的答案"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          disabled={busy || !!result}
          placeholder="写下你的思考…"
        />
      )}
      {!result && (
        <div className="button-row">
          <button
            className="primary"
            disabled={!answer.trim() || busy}
            onClick={() =>
              run(async () =>
                setResult(await onAnswer(item, answer, requestKey)),
              )
            }
          >
            {busy ? "处理中…" : "提交答案"}
            <ArrowRight size={15} />
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => run(async () => setHint(await onHint(item.id)))}
          >
            <CircleHelp size={15} /> 给我一点提示
          </button>
        </div>
      )}
      {hint && <p className="hint">{hint}</p>}
      {result && (
        <div className={"feedback " + (result.is_correct ? "correct" : "")}>
          <b>
            {result.is_correct === true
              ? "回答正确"
              : result.is_correct === false
                ? "再巩固一下"
                : "需要进一步评估"}
            {result.assistance_level === "hint" && " · 提示辅助"}
          </b>
          <p>{result.feedback}</p>
          <small>
            参考答案：{result.correct_answer} · 评分置信度：{result.confidence}
          </small>
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

function ProviderForm({ existing, demo, busy, onSubmit }) {
  const [kind, setKind] = useState(
    existing?.provider_type || "openai_compatible",
  );
  const [name, setName] = useState(existing?.name || ""),
    [url, setUrl] = useState(existing?.base_url || "https://api.openai.com/v1");
  const [model, setModel] = useState(existing?.chat_model || ""),
    [secret, setSecret] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState(
    existing?.embedding_model || "",
  );
  const isDemo = kind === "fake" || kind === "fake_files";
  const [consent, setConsent] = useState(false);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const body = {
          name: name || (isDemo ? "离线演示" : "我的模型"),
          chat_model: isDemo ? "demo-model" : model,
          embedding_model: embeddingModel || null,
          base_url: url,
        };
        if (!existing) body.provider_type = kind;
        if (secret || !existing) body.api_key = isDemo ? "demo" : secret;
        onSubmit(body);
      }}
    >
      <span className="eyebrow">BRING YOUR OWN KEY</span>
      <h2>{existing ? "更新模型连接" : "连接你的模型"}</h2>
      <p className="muted">凭证加密保存，所有教学调用使用你选择的模型。</p>
      {!existing && (
        <label>
          接口类型
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="openai_compatible">
              OpenAI-compatible 聊天接口
            </option>
            <option value="openai_files">
              原生 PDF（Files + Responses，需检测）
            </option>
            {demo && (
              <>
                <option value="fake">离线演示（固定操作系统样例）</option>
                <option value="fake_files">
                  资料演示（固定样例，未读取上传内容）
                </option>
              </>
            )}
          </select>
        </label>
      )}
      <label>
        连接名称
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如：我的学习模型"
          maxLength={100}
        />
      </label>
      {!isDemo ? (
        <>
          <label>
            Base URL
            <input
              required
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <label>
            聊天模型名称
            <input
              required
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="填写服务商提供的模型 ID"
              maxLength={200}
            />
          </label>
          <label>
            API Key
            <input
              required={!existing}
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={
                existing ? "留空保留当前密钥" : "仅发送至后端加密保存"
              }
              autoComplete="new-password"
            />
          </label>
          <label className="checkbox">
            <input
              required
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              我授权将学习目标、教学上下文和答案发送至此服务商；原生文件能力检测会上传随机标识测试
              PDF。调用可能产生费用，数据保留遵循其政策。
            </span>
          </label>
        </>
      ) : (
        <p className="hint">
          演示模式仅使用固定操作系统样例，不连接外部模型、不产生费用，不代表其他领域的真实教学结果。
        </p>
      )}
      {(kind === "openai_files" || kind === "fake_files") && (
        <label>
          远端 Embedding 模型（可选）
          <input
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
            maxLength={200}
            placeholder="留空使用关键词 + 模型精排"
          />
        </label>
      )}
      <button className="primary full" disabled={!!busy}>
        {busy || "保存模型连接"}
        <ArrowRight size={16} />
      </button>
    </form>
  );
}

function SpaceForm({ providers, busy, onSubmit }) {
  const available = providers.filter((p) => p.tested),
    [pid, setPid] = useState(available[0]?.id || "");
  const [goal, setGoal] = useState(""),
    [minutes, setMinutes] = useState(30),
    [date, setDate] = useState("");
  const [requestKey] = useState(key);
  const fake = available.find((p) => p.id === pid)?.provider_type === "fake";
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          provider_id: pid,
          goal,
          daily_minutes: Number(minutes),
          target_date: date || null,
          idempotency_key: requestKey,
        });
      }}
    >
      <span className="eyebrow">START WITH A GOAL</span>
      <h2>开启一段新的学习</h2>
      <p className="muted">告诉我们你想学什么，其余的交给学习框架。</p>
      <label>
        学习目标
        <input
          required
          minLength={2}
          maxLength={2000}
          placeholder="例如：系统学习操作系统"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
        />
      </label>
      <label>
        教学模型
        <select required value={pid} onChange={(e) => setPid(e.target.value)}>
          <option value="" disabled>
            选择已通过检测的模型
          </option>
          {available.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} · {p.chat_model}
            </option>
          ))}
        </select>
      </label>
      {!available.length && (
        <p className="hint">请先添加模型并完成连接测试，再创建学习空间。</p>
      )}
      {fake && (
        <p className="hint">
          此模型将载入固定操作系统演示课程。学习其他领域请接入真实模型。
        </p>
      )}
      <div className="form-row">
        <label>
          每日可用时间（分钟）
          <input
            type="number"
            min={5}
            max={480}
            required
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
          />
        </label>
        <label>
          目标日期（可选）
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
      </div>
      <p className="small muted">
        没有教材也可以开始。课程及测评答案由模型生成，考试大纲版本须另行核实。
      </p>
      <button className="primary full" disabled={!!busy || !pid}>
        {busy || "生成我的学习空间"}
        <ArrowRight size={16} />
      </button>
    </form>
  );
}

function Auth({ onLogin, config }) {
  const [register, setRegister] = useState(false),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState("");
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="auth-page">
      <section className="auth-story">
        <div className="brand">
          <span className="brand-icon">
            <Layers size={24} />
          </span>{" "}
          StudyAgent
        </div>
        <span className="eyebrow">YOUR KNOWLEDGE. YOUR PACE.</span>
        <h1>
          让每一步学习，
          <br />
          都有依据。
        </h1>
        <p>
          一个了解你的学习起点、记得你的进步，
          <br />
          并持续为你规划下一步的个人学习空间。
        </p>
        <div className="auth-visual">
          <span>01 / 确定目标</span>
          <span>02 / 发现起点</span>
          <span>
            03 / 循序向前 <ArrowUpRight size={20} />
          </span>
        </div>
        <small>BYOK · 持久化学习状态 · 可追溯的学习证据</small>
      </section>
      <section className="auth-form">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const u = await api(
                "/auth/" + (register ? "register" : "login"),
                { method: "POST", body: { username, password } },
              );
              await onLogin(u);
            } catch (err) {
              setError(err.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <span className="eyebrow">WELCOME TO YOUR NEXT CHAPTER</span>
          <h2>{register ? "创建你的学习账号" : "欢迎回到学习空间"}</h2>
          <p className="muted">
            {register
              ? "从今天开始，积累属于你的进步。"
              : "接上昨天的思路，继续今天的进步。"}
          </p>
          <label>
            用户名
            <input
              required
              minLength={3}
              maxLength={64}
              pattern="[a-zA-Z0-9_\-]+"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="3–64 位字母、数字、下划线"
            />
          </label>
          <label>
            密码
            <input
              required
              type="password"
              minLength={10}
              maxLength={128}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={register ? "new-password" : "current-password"}
              placeholder="至少 10 位"
            />
          </label>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button className="primary full" disabled={busy}>
            {busy ? "连接中…" : register ? "创建账号" : "进入学习空间"}
            <ArrowRight size={17} />
          </button>
          <p className="auth-switch">
            {register ? "已有账号？" : "第一次来？"}{" "}
            <button
              type="button"
              className="text-button"
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "登录" : "创建账号"}
            </button>
          </p>
          {config.demo_enabled && (
            <span className="demo-hint">
              <FlaskConical size={14} /> 当前允许无付费 Key 的离线演示
            </span>
          )}
        </form>
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
