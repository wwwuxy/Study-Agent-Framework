import React from "react";

export default function AlgorithmStatus({ algorithms }) {
  if (!algorithms) return null;
  return (
    <section className="card algorithm-status" aria-label="掌握评估与复习安排">
      <div className="section-head">
        <h3>让每一步学习有依据</h3>
        <span className="tag green">随学习记录更新</span>
      </div>
      <div className="algorithm-grid">
        <div>
          <b>知识掌握评估</b>
          <p>结合作答结果与提示使用情况，评估每个知识点的掌握程度。</p>
          <small>完成诊断和练习，逐步补充掌握依据。</small>
        </div>
        <div>
          <b>个性化复习安排</b>
          <p>根据实际回忆表现安排下次复习，帮助持续巩固记忆。</p>
          <small>复习到期是巩固提醒，不代表已经遗忘。</small>
        </div>
      </div>
      <p className="small muted">{algorithms.notice}</p>
    </section>
  );
}
