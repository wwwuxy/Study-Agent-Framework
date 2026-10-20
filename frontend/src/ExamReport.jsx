import React, { useState } from "react";
import { CheckCircle2, Download, FileText, ArrowRight } from "lucide-react";

const labels = {
  correct: "正确",
  incorrect: "错误",
  partial: "部分正确",
  unanswered: "未作答",
  uncertain: "待核对",
};
const states = { unknown: "待诊断", learning: "学习中", mastered: "已掌握" };
const confidence = { high: "高", medium: "中", low: "低" };
const number = (value) =>
  value === null || value === undefined ? "—" : String(value);

function QuestionReview({ question, concepts, onSave, busy }) {
  const q = question.current;
  const [result, setResult] = useState(q.result),
    [concept, setConcept] = useState(
      q.concept_ids.length === 1 ? q.concept_ids[0] : "",
    ),
    [score, setScore] = useState(q.score ?? ""),
    [maxScore, setMaxScore] = useState(q.max_score ?? ""),
    [error, setError] = useState("");
  return (
    <form
      className="exam-review-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        try {
          await onSave(question.id, {
            expected_version: question.version,
            result,
            concept_ids: concept ? [concept] : [],
            score: score === "" ? null : Number(score),
            max_score: maxScore === "" ? null : Number(maxScore),
          });
        } catch (err) {
          setError(err.message);
        }
      }}
    >
      <p className="small muted">
        对照原卷核对。原始批改不清晰时，手工改对错仅修订报告，不会增加掌握证据。
      </p>
      <label>
        核对结果
        <select value={result} onChange={(e) => setResult(e.target.value)}>
          {Object.entries(labels).map(([v, title]) => (
            <option key={v} value={v}>
              {title}
            </option>
          ))}
        </select>
      </label>
      <label>
        关联知识点
        <select value={concept} onChange={(e) => setConcept(e.target.value)}>
          <option value="">暂不关联</option>
          {concepts.map((c) => (
            <option key={c.key} value={c.key}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <div className="exam-score-inputs">
        <label>
          得分
          <input
            type="number"
            min="0"
            step="any"
            value={score}
            onChange={(e) => setScore(e.target.value)}
          />
        </label>
        <label>
          满分
          <input
            type="number"
            min="0.01"
            step="any"
            value={maxScore}
            onChange={(e) => setMaxScore(e.target.value)}
          />
        </label>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button disabled={busy}>保存核对结果</button>
    </form>
  );
}

export default function ExamReport({
  root,
  diagnostic,
  concepts = [],
  onUpdated,
  busy = false,
}) {
  const [filter, setFilter] = useState("all"),
    [preview, setPreview] = useState("");
  const report = diagnostic.report,
    counts = report.counts || {},
    names = Object.fromEntries(concepts.map((c) => [c.key, c.name]));
  const attachments = diagnostic.attachments;
  const image = attachments.find(
    (a) => a.id === preview && a.mime_type.startsWith("image/"),
  );
  const rows = diagnostic.questions.filter(
    (q) => filter === "all" || q.current.result === filter,
  );
  const changes = Object.entries(diagnostic.after).filter(
    ([key, value]) =>
      value.evidence_count !== diagnostic.before[key]?.evidence_count,
  );
  const fileUrl = (a) =>
    "/api/v1" +
    root +
    "/exam-diagnostics/" +
    diagnostic.id +
    "/attachments/" +
    a.id +
    "/download";
  return (
    <div className="exam-report">
      <section className="card">
        <span className="eyebrow">EXAM DIAGNOSIS</span>
        <h2>{diagnostic.name}</h2>
        <p className="small muted">
          考试日期：{diagnostic.exam_date || "未知，按导入顺序记录"} · 导入：
          {new Date(diagnostic.imported_at).toLocaleString()}
        </p>
        {diagnostic.is_demo && (
          <p className="hint">固定演示样例，未读取上传内容。</p>
        )}
        <div className="exam-metrics">
          <div>
            <strong>
              {number(report.stated_score)}
              <small> / {number(report.stated_max_score)}</small>
            </strong>
            <span>原卷标注成绩</span>
          </div>
          <div>
            <strong>
              {report.total_questions ?? 0}
              <small> 题</small>
            </strong>
            <span>识别叶子题目</span>
          </div>
          <div>
            <strong>
              {diagnostic.effective_evidence_count}
              <small> 条</small>
            </strong>
            <span>有效外部证据</span>
          </div>
        </div>
        <p className="small muted">
          逐题可核实得分合计：{number(report.verified_score_sum)}
          {!report.all_scores_known && "（部分题目缺少分值）"} ·
          可判定题正确率：
          {report.correctness_rate == null
            ? "暂无完整依据"
            : Math.round(report.correctness_rate * 100) + "%"}
        </p>
        {report.score_conflict && (
          <p className="hint">原卷标注总分与逐题加总不一致，请对照原卷核查。</p>
        )}
        {!report.coverage_complete && (
          <p className="hint">
            试卷识别可能不完整，未展示整卷正确率。{report.coverage_note}
          </p>
        )}
      </section>
      <section className="card exam-update">
        <div className="exam-card-heading">
          <CheckCircle2 size={19} />
          <h3>
            {diagnostic.effective_evidence_count
              ? "学习状态已更新"
              : "报告已生成，知识状态未更新"}
          </h3>
        </div>
        {changes.map(([key, after]) => (
          <div className="exam-state-row" key={key}>
            <b>{names[key] || key}</b>
            <span>
              {states[diagnostic.before[key]?.status] || "待诊断"}{" "}
              <ArrowRight size={13} /> {states[after.status]}
            </span>
            <small>
              {diagnostic.before[key]?.evidence_count || 0} →{" "}
              {after.evidence_count} 条有效证据
            </small>
          </div>
        ))}
        <p className="small muted">
          仅清晰的老师批改及明确的单知识点归因计入。辅助程度未知，不计为独立答对；试卷导入不重置复习时间。
        </p>
        {report.next_action && (
          <p>
            <b>下一步：</b>
            {report.next_action.reason}
          </p>
        )}
      </section>
      <section className="card">
        <div className="exam-card-heading">
          <FileText size={19} />
          <h3>原卷与批改依据</h3>
        </div>
        <div className="exam-file-links">
          {attachments.map((a, i) => (
            <div key={a.id}>
              <a href={fileUrl(a)} download>
                <Download size={14} />{" "}
                {a.mime_type === "application/pdf"
                  ? "下载原卷"
                  : `第 ${i + 1} 张`}{" "}
                · {a.filename}
              </a>
              {a.mime_type.startsWith("image/") && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setPreview(preview === a.id ? "" : a.id)}
                >
                  {preview === a.id ? "收起" : "预览"}
                </button>
              )}
            </div>
          ))}
        </div>
        {image && (
          <img
            className="exam-original-preview"
            src={fileUrl(image)}
            alt={`原卷 ${image.filename}`}
          />
        )}
      </section>
      {report.advice && (
        <section className="card">
          <h3>诊断与巩固建议</h3>
          <p className="exam-prewrap">{report.advice.summary}</p>
          {report.advice_stale && (
            <p className="hint">
              以下模型建议基于首次识别；核对后请以最新逐题记录和系统下一步为准。
            </p>
          )}
          {report.advice.suggestions?.map((s, i) => (
            <article className="exam-suggestion" key={i}>
              <b>
                {s.concept_ids.map((id) => names[id] || id).join("、") ||
                  "学习建议"}
              </b>
              <p>{s.reason}</p>
              <p>{s.action}</p>
              <small className="muted">
                依据题目：{s.question_ids.join("、") || "整卷表现"} ·
                模型建议，需结合原题核实
              </small>
            </article>
          ))}
        </section>
      )}
      <section className="card">
        <h3>知识点表现</h3>
        {Object.entries(report.concepts || {}).length ? (
          Object.entries(report.concepts).map(([key, value]) => (
            <div className="exam-state-row" key={key}>
              <b>{names[key] || key}</b>
              <small>
                正确 {value.correct} · 错误 {value.incorrect} · 部分正确{" "}
                {value.partial} · 待核对 {value.uncertain}
              </small>
            </div>
          ))
        ) : (
          <p className="muted">
            暂无可关联的现有知识点；试卷内容不会自动增加课程节点。
          </p>
        )}
      </section>
      <section className="card">
        <div className="exam-question-heading">
          <h3>逐题诊断</h3>
          <label>
            筛选
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">全部（{diagnostic.questions.length}）</option>
              {Object.entries(labels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}（{counts[value] || 0}）
                </option>
              ))}
            </select>
          </label>
        </div>
        {rows.map((item) => {
          const q = item.current;
          return (
            <article key={item.id} className="exam-question">
              <div className="exam-question-title">
                <b>第 {q.number} 题</b>
                <span className={"exam-result " + q.result}>
                  {labels[q.result]}
                </span>
                <span>
                  {number(q.score)} / {number(q.max_score)}
                </span>
              </div>
              <p className="exam-prewrap">
                {q.prompt || "题干未完整识别，请查看原卷"}
              </p>
              <dl className="exam-answer">
                <dt>学生答案</dt>
                <dd>{q.student_answer || "未识别到明确答案"}</dd>
                <dt>老师批改</dt>
                <dd>{q.teacher_marks || "缺少明确批改"}</dd>
              </dl>
              <p className="small muted">
                关联：
                {q.concept_ids.map((id) => names[id] || id).join("、") ||
                  "未关联"}{" "}
                · 识别置信度：{confidence[q.recognition_confidence]} ·
                映射置信度：{confidence[q.mapping_confidence]}
              </p>
              <p className="small muted">
                来源：
                {attachments.find((a) => a.client_id === q.source_id)
                  ?.filename || q.source_id}
                {q.page ? ` · 模型提供第 ${q.page} 页（未核实）` : ""}
              </p>
              {q.notes?.length > 0 && (
                <p className="hint">{q.notes.join("；")}</p>
              )}
              <p
                className={
                  "small " + (item.event_id ? "exam-evidence-added" : "muted")
                }
              >
                {item.event_id
                  ? "已计入有效外部证据"
                  : item.exclusion_reason || "未计入有效证据"}
              </p>
              {!item.event_id && (
                <details>
                  <summary>核对这道题</summary>
                  <QuestionReview
                    key={item.id + ":" + item.version}
                    question={item}
                    concepts={concepts}
                    onSave={onUpdated}
                    busy={busy}
                  />
                  {item.version > 1 && (
                    <p className="small muted">
                      已保存用户核对；原始识别：{labels[item.original.result]}
                      ，原得分 {number(item.original.score)} /{" "}
                      {number(item.original.max_score)}。
                    </p>
                  )}
                </details>
              )}
            </article>
          );
        })}
        {!rows.length && <p className="muted">此筛选下暂无题目。</p>}
      </section>
    </div>
  );
}
