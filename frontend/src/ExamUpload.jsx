import React, { useEffect, useState } from "react";
import ActionButton from "./ActionButton";
import { Upload, FileText, ArrowUp, ArrowDown } from "lucide-react";

export default function ExamUpload({
  capabilities,
  onUpload,
  busy,
  uploading,
}) {
  const [files, setFiles] = useState([]),
    [name, setName] = useState(""),
    [examDate, setExamDate] = useState(""),
    [consent, setConsent] = useState(false),
    [error, setError] = useState(""),
    [previews, setPreviews] = useState([]);
  useEffect(() => {
    const urls = files.map((file) =>
      file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
    );
    setPreviews(urls);
    return () => urls.forEach((url) => url && URL.revokeObjectURL(url));
  }, [files]);
  const supported =
    capabilities && (capabilities.pdf || capabilities.images.length > 0);
  const accepts = [
    ...(capabilities?.pdf ? ["application/pdf"] : []),
    ...(capabilities?.images || []),
  ].join(",");
  function choose(items) {
    setError("");
    setConsent(false);
    if (!items.length) {
      setFiles([]);
      return;
    }
    const types = items.map(
      (file) =>
        file.type ||
        (file.name.toLowerCase().endsWith(".pdf")
          ? "application/pdf"
          : file.name.toLowerCase().endsWith(".png")
            ? "image/png"
            : "image/jpeg"),
    );
    if (
      items.length > capabilities.max_images ||
      items.some((file) => file.size > capabilities.max_bytes) ||
      items.reduce((sum, file) => sum + file.size, 0) >
        capabilities.max_total_bytes
    ) {
      setError("文件大小或数量超过限制");
      return;
    }
    if (
      types.some((t) => !accepts.split(",").includes(t)) ||
      (types.includes("application/pdf") && items.length !== 1)
    ) {
      setError("请选择一个 PDF，或一组已支持的 JPG／PNG 图片");
      return;
    }
    setFiles(items);
    if (!name) setName(items[0].name.replace(/\.[^.]+$/, ""));
  }
  function move(index, step) {
    setFiles((old) => {
      const rows = [...old];
      [rows[index], rows[index + step]] = [rows[index + step], rows[index]];
      return rows;
    });
  }
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
  return (
    <section className="card exam-upload">
      <div className="exam-card-heading">
        <Upload size={19} />
        <h3>上传已批改试卷</h3>
      </div>
      <p className="small muted">
        识别模型：{capabilities?.provider_name || "正在读取配置"}
      </p>
      {capabilities?.is_demo && (
        <p className="hint">
          离线演示使用固定样例，未读取上传内容，不代表真实识别能力。
        </p>
      )}
      {!supported && capabilities && (
        <p className="hint">
          请在「模型与设置」中选择并检测支持 PDF 或图片理解的用户模型。
        </p>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          try {
            await onUpload(
              files,
              {
                name: name.trim() || "已批改试卷",
                exam_date: examDate || null,
              },
              consent,
            );
            setConsent(false);
          } catch (err) {
            setError(err.message);
          }
        }}
      >
        <label className="exam-drop">
          <FileText size={28} />
          <span>选择 PDF 或多页照片</span>
          <small>
            一个 PDF 或最多 {capabilities?.max_images || 20} 张 JPG／PNG
          </small>
          <input
            type="file"
            accept={accepts}
            multiple
            disabled={!supported || busy}
            onChange={(e) => choose([...e.target.files])}
          />
        </label>
        {files.length > 0 && (
          <ol className="exam-file-list">
            {files.map((file, i) => (
              <li key={`${file.name}-${i}`}>
                {previews[i] && (
                  <img src={previews[i]} alt={`试卷第 ${i + 1} 张缩略图`} />
                )}
                <span>
                  {i + 1}. {file.name}
                  <small>{(file.size / 1048576).toFixed(2)} MiB</small>
                </span>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`第 ${i + 1} 页上移`}
                  disabled={busy || i === 0}
                  onClick={() => move(i, -1)}
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`第 ${i + 1} 页下移`}
                  disabled={busy || i === files.length - 1}
                  onClick={() => move(i, 1)}
                >
                  <ArrowDown size={14} />
                </button>
              </li>
            ))}
          </ol>
        )}
        <label>
          试卷名称
          <input
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
            placeholder="例如：数学期中测试"
          />
        </label>
        <label>
          考试日期（可留空）
          <input
            type="date"
            max={today}
            value={examDate}
            onChange={(e) => setExamDate(e.target.value)}
            disabled={busy}
          />
        </label>
        <p className="small muted">
          单文件上限{" "}
          {Math.round((capabilities?.max_bytes || 20971520) / 1048576)}{" "}
          MiB，总上限{" "}
          {Math.round((capabilities?.max_total_bytes || 41943040) / 1048576)}{" "}
          MiB。未知日期会按导入顺序记录。
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            disabled={busy}
          />
          同意将本次试卷交给当前用户模型处理，知悉可能产生的费用及服务商保留政策。
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <ActionButton
          className="primary"
          disabled={!supported || busy || !files.length || !consent}
          loading={uploading}
          loadingText="正在上传试卷并提交诊断…"
        >
          <Upload size={16} /> 上传并诊断
        </ActionButton>
      </form>
    </section>
  );
}
