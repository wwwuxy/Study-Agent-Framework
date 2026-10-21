import ActionButton, { LoadingNotice } from "./ActionButton";
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
  FileText,
  FolderOpen,
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
  MessageCircle,
  CalendarDays,
  Activity,
} from "lucide-react";
import { api, key, advanceSessionScope, onSessionExpired } from "./api";
import AuthPage from "./AuthPage";
import { authRoute, navigateAuth } from "./authRouting";
import { createLatestRequest } from "./latestRequest";
import "./styles.css";
import Materials, { Citations } from "./Materials";
import ProviderForm from "./ProviderForm";
import {
  imageProbeErrors,
  providerCapabilityLabels,
} from "./providerCapabilities";
import SpaceManager from "./SpaceManager";
import Reviews from "./Reviews";
import LearningReport from "./LearningReport";
import AlgorithmStatus from "./AlgorithmStatus";
import PlanningChat from "./PlanningChat";
import ExamDiagnostics from "./ExamDiagnostics";
import KnowledgeMindMap from "./KnowledgeMindMap";
import DailyTasks from "./DailyTasks";
import WeeklySummaries from "./WeeklySummaries";
import ActivityRuns from "./ActivityRuns";
import PageTabs from "./PageTabs";

const labels = { unknown: "待诊断", learning: "学习中", mastered: "已掌握" };
const actions = {
  DIAGNOSE: "初始诊断",
  LEARN_CONCEPT: "学习新知",
  REMEDIATE: "修复误区",
  PRACTICE: "定向练习",
  ASSESS: "迁移与阶段测评",
  REVIEW: "间隔复习",
};
const runLabels = {
  probe: "检测模型连接",
  curriculum: "生成课程",
  diagnostic: "生成诊断题",
  lesson: "生成课堂内容",
  grade: "评阅作答",
  hint: "生成学习提示",
  material_upload: "上传教材",
  material_outline: "提取教材目录",
  material_section: "整理教材章节",
  material_embedding: "建立教材检索索引",
  material_rerank: "筛选教材内容",
  material_delete: "清理远端教材",
  exam_diagnostic: "识别与诊断试卷",
  planning_chat: "学习计划对话",
  m4_analysis: "AI 学习分析",
};
const eventLabels = {
  diagnostic_submitted: "完成诊断",
  exam_question_imported: "导入试卷作答",
  exam_diagnostic_deleted: "删除诊断并撤回导入证据",
  assessment_submitted: "提交练习",
  lesson_viewed: "阅读讲解",
  hint_requested: "请求提示",
  plan_adjusted: "调整学习计划",
  requirements_changed: "通过对话调整学习需求",
  review_submitted: "完成回忆练习",
  learning_task_started: "开始学习任务",
  learning_task_completed: "完成课堂与练习",
};

function App() {
  const [settingsSection, setSettingsSection] = useState("models"),
    [reportSection, setReportSection] = useState("overview");
  const [route, setRoute] = useState(() => authRoute(window.location.pathname));
  const [user, setUser] = useState(null),
    [ready, setReady] = useState(false);
  const [config, setConfig] = useState({}),
    [spaces, setSpaces] = useState([]),
    [providers, setProviders] = useState([]);
  const [sid, setSid] = useState(""),
    [page, setPage] = useState("report"),
    [modal, setModal] = useState("");
  const [detail, setDetail] = useState(null),
    [diagnosis, setDiagnosis] = useState(null),
    [lesson, setLesson] = useState(null);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const spaceReads = useRef(createLatestRequest()),
    listReads = useRef(createLatestRequest()),
    lessonStart = useRef(null);
  const activeSpace = useRef(sid),
    sessionScope = useRef(createLatestRequest()),
    operation = useRef(0);
  activeSpace.current = sid;
  function openOverview() {
    setReportSection("overview");
    setPage("report");
  }
  function openReviews() {
    setReportSection("reviews");
    setPage("report");
  }
  function selectSpace(id) {
    if (activeSpace.current !== id) {
      spaceReads.current.invalidate();
    }
    activeSpace.current = id;
    setSid(id);
  }
  function invalidateSession() {
    setSettingsSection("models");
    advanceSessionScope();
    setBusy("");
    setError("");
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
    openOverview();
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
          api(root + "/reviews"),
        ]),
      ([concepts, profile, action, events, runs, plan, current, reviews]) => {
        if (id !== activeSpace.current) return;
        setDetail({ concepts, profile, action, events, runs, plan, reviews });
        setLesson(current);
      },
    );
  }
  async function removeSpace(id) {
    const isCurrent = sessionScope.current.checkpoint();
    setError("");
    await api("/study-spaces/" + id, { method: "DELETE" });
    if (!isCurrent()) return false;
    listReads.current.invalidate();
    setSpaces((items) => items.filter((item) => item.id !== id));
    if (activeSpace.current === id) {
      selectSpace(spaces.find((item) => item.id !== id)?.id || "");
      setDetail(null);
      setLesson(null);
      setDiagnosis(null);
    }
    try {
      await refreshLists();
    } catch (err) {
      if (isCurrent())
        setError("空间已永久删除，但列表刷新失败：" + err.message);
    }
    return isCurrent();
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
    const changed = () => setRoute(authRoute(window.location.pathname));
    window.addEventListener("popstate", changed);
    return () => window.removeEventListener("popstate", changed);
  }, []);
  useEffect(
    () =>
      onSessionExpired(() => {
        setUser(null);
        invalidateSession();
        navigateAuth("login", { replace: true });
      }),
    [],
  );
  useEffect(() => {
    if (!ready) return;
    if (user && route !== "workspace")
      navigateAuth("workspace", { replace: true });
    if (!user && route === "workspace")
      navigateAuth("login", { replace: true });
  }, [ready, user, route]);
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
  useEffect(() => {
    if (page === "classroom" && !diagnosis && lesson?.id)
      lessonStart.current?.scrollIntoView({
        block: "start",
        behavior: "smooth",
      });
  }, [lesson?.id, page, diagnosis]);
  const root = "/study-spaces/" + sid;
  const stats = detail?.profile.states || [];
  const mastered = stats.filter((s) => s.status === "mastered").length;
  const currentProvider = providers.find((p) => p.id === space?.provider_id);
  const pendingExercises =
    lesson?.exercises.filter((item) => !lesson.attempts?.[item.id]).length || 0;
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
  async function openActivityTask(receipt) {
    const current = sessionScope.current.checkpoint(),
      id = sid;
    if (receipt.execution_kind === "diagnostic") {
      const result = await api(root + "/diagnostics", { method: "POST" });
      if (!current() || id !== activeSpace.current) return;
      setDiagnosis(result);
    } else setDiagnosis(null);
    await refreshSpace(id);
    if (current() && id === activeSpace.current) setPage("classroom");
  }
  async function openReview(review) {
    setLesson(review.lesson);
    setDiagnosis(null);
    setPage("classroom");
    await refreshSpace();
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
  async function nextLesson() {
    if (!lesson || busy) return;
    if (pendingExercises) {
      setError(
        `还有 ${pendingExercises} 道练习未提交，请先完成作答，再开始下一次学习。`,
      );
      return;
    }
    const isCurrent = sessionScope.current.checkpoint(),
      id = sid;
    if (!lesson.completed) {
      const saved = await work("记录本次阅读", async () => {
        await api(root + "/lessons/" + lesson.id + "/complete", {
          method: "POST",
          body: { idempotency_key: key() },
        });
        if (!isCurrent() || id !== activeSpace.current) return false;
        setLesson((current) =>
          current?.id === lesson.id ? { ...current, completed: true } : current,
        );
        return true;
      });
      if (!saved) return;
    }
    if (isCurrent() && id === activeSpace.current) await beginLesson();
  }
  async function answered(item, answer, requestKey, memoryRating = null) {
    const isCurrent = sessionScope.current.checkpoint(),
      id = sid;
    const result = await api(root + "/attempts", {
      method: "POST",
      body: {
        item_id: item.id,
        answer,
        idempotency_key: requestKey,
        memory_rating: memoryRating,
      },
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
      <AuthPage
        mode={route === "register" ? "register" : "login"}
        onModeChange={navigateAuth}
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
            openOverview();
          }}
        >
          <span className="brand-icon">
            <Layers size={22} />
          </span>{" "}
          StudyAgent<span className="brand-dot">®</span>
        </a>
        <div className="workspace-label">你的个人学习空间</div>
        {spaces.length ? (
          <>
            <select
              className="space-select"
              aria-label="选择学习空间"
              value={sid}
              onChange={(e) => {
                selectSpace(e.target.value);
                openOverview();
              }}
            >
              {spaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.goal}
                </option>
              ))}
            </select>
            <LoadingNotice active={busy === "读取学习进度"}>
              正在读取此空间的学习进度…
            </LoadingNotice>
            <button className="new-space" onClick={() => setModal("space")}>
              <Plus size={15} /> 新建学习空间
            </button>
          </>
        ) : (
          <button
            type="button"
            className="space-select space-create"
            onClick={() => setModal("space")}
          >
            <Plus size={15} /> 创建你的学习空间
          </button>
        )}
        <div className="nav-label">你的学习</div>
        <nav>
          {[
            ["today", CalendarDays, "今日任务"],
            ["chat", MessageCircle, "学习对话"],
            ["classroom", Sparkles, "专属课堂"],
            ["knowledge", Network, "知识地图"],
            ["materials", Layers, "私人教材"],
            ["report", Target, "学习概要"],
            ["exams", FileText, "成绩诊断"],
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
              <small>自选模型 · 独立空间 · 进度留存</small>
            </span>
          </div>
          <div className="user">
            <span className="avatar">{user.username[0].toUpperCase()}</span>
            <span>
              {user.username}
              <small>个人学习者</small>
            </span>
            <ActionButton
              loadingText="正在退出…"
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
            </ActionButton>
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
                  today: "今日任务",
                  chat: "学习对话",
                  classroom: "专属课堂",
                  knowledge: "知识地图",
                  materials: "私人教材",
                  exams: "成绩诊断",
                  report: "学习概要",
                  settings: "模型与设置",
                }[page]
              }
            </b>
          </span>
          <span className="phase">
            <span /> 围绕目标，持续进步
          </span>
        </header>
        <div className="main-content">
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => setError("")}>×</button>
            </div>
          )}
          {page === "settings" ? (
            <>
              <PageTitle
                eyebrow="模型连接 · 空间管理 · 运行记录"
                title="模型与设置"
                subtitle="统一管理模型连接、学习空间与后台运行。"
              />
              <PageTabs
                label="设置分类"
                value={settingsSection}
                onChange={setSettingsSection}
                tabs={[
                  { id: "models", label: "模型连接", icon: Cpu },
                  { id: "spaces", label: "学习空间", icon: FolderOpen },
                  { id: "activity", label: "后台运行", icon: Activity },
                ]}
              >
                {settingsSection === "spaces" ? (
                  <SpaceManager
                    key={user.id}
                    embedded
                    currentSpaceId={sid}
                    providers={providers}
                    onOpen={(id) => {
                      selectSpace(id);
                      openOverview();
                    }}
                    onCreate={() => setModal("space")}
                    onRemove={removeSpace}
                  />
                ) : settingsSection === "activity" ? (
                  <ActivityRuns key={user.id} embedded />
                ) : (
                  <>
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
                            <span>
                              聊天 {p.capabilities.chat ? "✓" : "待验证"}
                            </span>
                            <span>
                              图像理解：{providerCapabilityLabels(p).image}
                            </span>
                            <span>
                              PDF 文件理解：{providerCapabilityLabels(p).pdf}
                            </span>
                            <span>
                              远端 Embedding：
                              {p.capabilities.embedding
                                ? "已验证"
                                : "未验证或不支持"}
                            </span>
                            {p.capabilities.is_demo && (
                              <span>固定演示 · 未读取文件内容</span>
                            )}
                            {p.capabilities.file_error && (
                              <span>文件检测：{p.capabilities.file_error}</span>
                            )}
                            {Object.entries(
                              p.capabilities.image_errors || {},
                            ).map(([mime, code]) => (
                              <span key={mime}>
                                {mime === "image/png" ? "PNG" : "JPEG"} 检测：
                                {imageProbeErrors[code] || code}
                              </span>
                            ))}
                            {p.capabilities.retention_warning && (
                              <span>{p.capabilities.retention_warning}</span>
                            )}
                          </div>
                          <div className="button-row">
                            <ActionButton
                              loadingText="正在测试连接…"
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
                            </ActionButton>
                            <button onClick={() => setModal(p)}>
                              编辑凭证
                            </button>
                            <ActionButton
                              loadingText="正在删除模型…"
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
                            </ActionButton>
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
                            .filter(
                              (p) => p.tested || p.id === space.provider_id,
                            )
                            .map((p) => (
                              <option
                                key={p.id}
                                value={p.id}
                                disabled={!p.tested}
                              >
                                {p.name} · {p.chat_model}
                                {!p.tested ? "（需要重新检测）" : ""}
                              </option>
                            ))}
                        </select>
                        <LoadingNotice active={busy === "切换教学模型"}>
                          正在切换教学模型，保留现有学习进度…
                        </LoadingNotice>
                        {currentProvider?.provider_type === "fake" && (
                          <p className="hint">
                            当前为离线演示，使用固定操作系统样例。
                          </p>
                        )}
                      </section>
                    )}
                    <p className="muted small">
                      API Key
                      只在后端加密保存。连接测试与教学会向你选择的服务发送请求并可能产生费用。令牌用量见「学习概要
                      → 学习记录」，金额以服务商账单为准。
                    </p>
                  </>
                )}
              </PageTabs>
            </>
          ) : !space ? (
            <div className="empty-space">
              <span className="eyebrow">连接模型，开启学习</span>
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
                <span>确定目标 → 诊断起点 → 循序学习</span>
              </div>
            </div>
          ) : !detail ? (
            <div className="loading">
              <LoaderCircle className="spin" /> 正在读取进度
            </div>
          ) : (
            <>
              {page === "today" && (
                <DailyTasks
                  key={user.id + sid}
                  root={root}
                  onStarted={openActivityTask}
                  onReviewStarted={openReview}
                  onViewReviews={openReviews}
                />
              )}
              {page === "chat" && (
                <PlanningChat
                  key={user.id + sid}
                  root={root}
                  plan={detail.plan}
                  concepts={detail.concepts}
                  onPlanChanged={async () => {
                    await refreshLists();
                    await refreshSpace();
                  }}
                  onLessonResumed={async (value) => {
                    setLesson(value);
                    setDiagnosis(null);
                    setPage("classroom");
                    await refreshSpace();
                  }}
                />
              )}
              {page === "classroom" && (
                <button className="chat-entry" onClick={() => setPage("chat")}>
                  <MessageCircle size={18} /> 需求变了？和助手聊聊，调整学习计划{" "}
                  <ArrowRight size={16} />
                </button>
              )}
              {page === "report" && (
                <>
                  <PageTitle
                    eyebrow="学习进度 · 复习安排 · 历史记录"
                    title="学习概要"
                    subtitle="查看知识掌握情况、近期作答和复习安排，决定下一步学什么。"
                  />
                  <PageTabs
                    label="报告分类"
                    value={reportSection}
                    onChange={setReportSection}
                    tabs={[
                      { id: "overview", label: "学习概览", icon: BookOpen },
                      { id: "recent", label: "近期统计", icon: Target },
                      { id: "weekly", label: "自然周报", icon: CalendarDays },
                      { id: "reviews", label: "间隔复习", icon: History },
                      { id: "history", label: "学习记录", icon: History },
                    ]}
                  >
                    {reportSection === "overview" && (
                      <>
                        <div className="section-intro">
                          <h2>让学习，循序向前。</h2>
                          <p>
                            从当前目标和作答表现出发，查看进度与下一步建议。
                          </p>
                        </div>
                        <button
                          className="chat-entry"
                          onClick={() => setPage("chat")}
                        >
                          <MessageCircle size={18} />{" "}
                          需求变了？和助手聊聊，调整学习计划{" "}
                          <ArrowRight size={16} />
                        </button>
                        <AlgorithmStatus
                          algorithms={detail.profile.algorithms}
                        />
                        <button
                          className="review-callout"
                          onClick={openReviews}
                        >
                          到期复习 {detail.reviews?.due.length || 0} 项 ·
                          查看复习安排 <ArrowRight size={16} />
                        </button>
                        <div className="hero-grid">
                          <section className="hero">
                            <div className="hero-top">
                              <span className="tag pale">正在学习</span>
                              <span className="hero-index">
                                学习空间 /{" "}
                                {String(spaces.indexOf(space) + 1).padStart(
                                  2,
                                  "0",
                                )}
                              </span>
                            </div>
                            <h2>{space.goal}</h2>
                            <p>
                              每天 {space.daily_minutes} 分钟 ·{" "}
                              {space.expected_level}
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
                              <ActionButton
                                loadingText="正在准备学习内容…"
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
                              </ActionButton>
                            </div>
                            <div className="hero-decoration">
                              <div />
                              <div />
                              <div />
                            </div>
                          </section>
                          <section className="card next-card">
                            <div className="eyebrow">
                              <span className="orange-dot" /> 根据当前表现推荐
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
                              <span>
                                约 {detail.action.estimated_minutes} 分钟
                              </span>
                              <span>
                                {detail.action.evidence_event_ids.length} 条依据
                              </span>
                            </div>
                            <ActionButton
                              loadingText="正在准备学习内容…"
                              className="text-button"
                              disabled={!!busy}
                              onClick={
                                detail.action.action === "DIAGNOSE"
                                  ? beginDiagnosis
                                  : beginLesson
                              }
                            >
                              开始这一步 <ArrowRight size={17} />
                            </ActionButton>
                          </section>
                        </div>
                        <div className="metrics">
                          <Metric
                            label="课程知识点"
                            value={stats.length}
                            unit="个"
                            detail="由模型生成，随学习逐步核实"
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
                            label="每日学习时间"
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
                                state={stats.find(
                                  (s) => s.concept_id === c.key,
                                )}
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
                              <Check size={15} /> 学习进度自动保存，下次接着学
                            </div>
                            <div>
                              <Check size={15} /> 每一步推荐，都能查看安排理由
                            </div>
                            <div>
                              <Check size={15} /> 未验证的知识明确标注
                            </div>
                          </section>
                        </div>
                      </>
                    )}
                    {reportSection === "recent" && (
                      <LearningReport
                        key={user.id + sid}
                        root={root}
                        embedded
                      />
                    )}
                    {reportSection === "weekly" && (
                      <WeeklySummaries
                        key={user.id + sid}
                        embedded
                        root={root}
                        onRolling={() => setReportSection("recent")}
                      />
                    )}
                    {reportSection === "reviews" && (
                      <Reviews
                        key={user.id + sid}
                        root={root}
                        embedded
                        onStarted={openReview}
                      />
                    )}
                    {reportSection === "history" && (
                      <>
                        <div className="section-intro">
                          <h2>每一步，都留下记录</h2>
                          <p>
                            回看诊断、课堂和练习记录，查看模型用量与每次安排的依据。
                          </p>
                        </div>
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
                              <span>{runLabels[r.step] || "模型处理"}</span>
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
                  </PageTabs>
                </>
              )}
              {page === "exams" && (
                <ExamDiagnostics
                  key={user.id + sid}
                  root={root}
                  concepts={detail.concepts}
                  onStateChanged={() => refreshSpace(sid)}
                />
              )}
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
              {page === "knowledge" && (
                <>
                  <PageTitle
                    eyebrow="知识结构 · 前置关系 · 掌握状态"
                    title="你的知识地图"
                    subtitle="查看目标所需的知识点与前置关系，点击节点了解学习内容和掌握情况。"
                  />
                  <KnowledgeMindMap
                    key={sid}
                    concepts={detail.concepts}
                    states={stats}
                    goal={space?.goal || "我的学习目标"}
                  />
                </>
              )}
              {page === "classroom" && (
                <>
                  <PageTitle
                    eyebrow="诊断起点 · 理解概念 · 练习巩固"
                    title="专属课堂"
                    subtitle="先了解学习起点，再通过讲解、示例和练习逐步掌握知识。"
                  />
                  <div className="button-row classroom-tabs">
                    <ActionButton
                      loadingText="正在生成诊断题…"
                      onClick={beginDiagnosis}
                      disabled={!!busy}
                    >
                      初始诊断
                    </ActionButton>
                    <ActionButton
                      loadingText="正在准备课堂…"
                      className="primary"
                      onClick={beginLesson}
                      disabled={!!busy}
                    >
                      开始 / 继续课堂 <Sparkles size={15} />
                    </ActionButton>
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
                      <ActionButton
                        loadingText="正在准备课堂…"
                        className="primary"
                        onClick={beginLesson}
                      >
                        进入课堂 <ArrowRight size={16} />
                      </ActionButton>
                    </section>
                  ) : lesson ? (
                    <section className="card lesson" ref={lessonStart}>
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
                      <ActionButton
                        loadingText="正在记录阅读…"
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
                      </ActionButton>
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
                      <div className="lesson-next" aria-live="polite">
                        <p className="small muted">
                          {pendingExercises
                            ? `还有 ${pendingExercises} 道练习待提交，完成后即可继续。`
                            : lesson.completed
                              ? "本次阅读和练习已完成，可以开始下一次学习。"
                              : "练习已全部提交。点击继续将确认本次讲解已读，并准备下一次学习。"}
                        </p>
                        {error && <p className="error">{error}</p>}
                        <ActionButton
                          loadingText="正在准备下一次学习…"
                          className="primary"
                          disabled={!!busy}
                          onClick={nextLesson}
                        >
                          下一次学习 <ArrowRight size={16} />
                        </ActionButton>
                      </div>
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
            </>
          )}
          <footer>
            <span>StudyAgent Framework</span>
            <span>以目标为起点，以证据为方向。</span>
            <span>自选模型 · 持续学习</span>
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
                    openOverview();
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
  const [memoryRating, setMemoryRating] = useState("");
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
      {!result && item.purpose === "review" && (
        <label className="memory-rating">
          回忆难度（可选）
          <select
            aria-label="回忆难度"
            value={memoryRating}
            disabled={busy}
            onChange={(e) => setMemoryRating(e.target.value)}
          >
            <option value="">自动根据作答结果安排复习</option>
            <option value="again">没有独立想起</option>
            <option value="hard" disabled={!!hint}>
              独立想起，但很费力
            </option>
            <option value="good" disabled={!!hint}>
              独立想起
            </option>
            <option value="easy" disabled={!!hint}>
              轻松独立想起
            </option>
          </select>
          <small>按实际回忆情况选择；系统会结合作答结果安排下次复习。</small>
        </label>
      )}
      {!result && (
        <div className="button-row">
          <ActionButton
            loadingText="正在提交答案…"
            className="primary"
            disabled={!answer.trim() || busy}
            onClick={() =>
              run(async () =>
                setResult(
                  await onAnswer(
                    item,
                    answer,
                    requestKey,
                    memoryRating || null,
                  ),
                ),
              )
            }
          >
            提交答案
            <ArrowRight size={15} />
          </ActionButton>
          <ActionButton
            loadingText="正在获取提示…"
            className="text-button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                setHint(await onHint(item.id));
                setMemoryRating("");
              })
            }
          >
            <CircleHelp size={15} /> 给我一点提示
          </ActionButton>
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
          {result.memory && (
            <p className="small">
              复习安排：{result.memory.reason} · 下次复习{" "}
              {new Date(result.memory.due).toLocaleString("zh-CN")}
            </p>
          )}
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

function SpaceForm({ providers, busy, onSubmit }) {
  const available = providers.filter((p) => p.tested),
    [pid, setPid] = useState(available[0]?.id || "");
  const [goal, setGoal] = useState("");
  const [requestKey] = useState(key);
  const fake = available.find((p) => p.id === pid)?.provider_type === "fake";
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          provider_id: pid,
          goal,
          idempotency_key: requestKey,
        });
      }}
    >
      <span className="eyebrow">一个目标，一个独立的学习空间</span>
      <h2>开启一段新的学习</h2>
      <p className="muted">
        写下想学的内容，助手会据此生成课程，并通过诊断安排学习起点。
      </p>
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
      <p className="small muted">
        没有教材也可以开始，之后可在「私人教材」补充资料。模型生成的课程与答案请结合教材核对。
      </p>
      <ActionButton
        className="primary full"
        disabled={!!busy || !pid}
        loading={!!busy}
        loadingText="正在生成课程与学习空间…"
      >
        生成我的学习空间 <ArrowRight size={16} />
      </ActionButton>
    </form>
  );
}

createRoot(document.getElementById("root")).render(<App />);
