export async function hashExamFile(file) {
  const bytes = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)]
    .map((v) => v.toString(16).padStart(2, "0"))
    .join("");
}

export function createExamDiagnosticState({
  api,
  makeKey = () => crypto.randomUUID(),
  hashFile = hashExamFile,
}) {
  let generation = 0,
    scope = null,
    pending = null;
  const patches = new Map(),
    actionKeys = new Map(),
    removed = new Set();
  function enter(root) {
    if (root !== scope) {
      generation++;
      scope = root;
      pending = null;
      patches.clear();
      actionKeys.clear();
      removed.clear();
    }
    const ticket = generation;
    return () => ticket === generation && root === scope;
  }
  return {
    invalidate() {
      generation++;
      pending = null;
      patches.clear();
      actionKeys.clear();
    },
    async action(
      root,
      diagnostic,
      action,
      consent,
      onCurrent,
      method = "POST",
    ) {
      const current = enter(root);
      const identity = JSON.stringify([
        root,
        diagnostic.id,
        diagnostic.version,
        action,
        consent,
      ]);
      if (!actionKeys.has(identity)) actionKeys.set(identity, makeKey());
      const result = await api(
        `${root}/exam-diagnostics/${diagnostic.id}/${action}`,
        {
          method,
          ...(action === "start" || action === "retry"
            ? { body: { consent, idempotency_key: actionKeys.get(identity) } }
            : {}),
        },
      );
      if (!current()) return;
      // An acknowledged operation is finished. A later deliberate retry is new;
      // only an uncertain network outcome should retain the old request key.
      actionKeys.delete(identity);
      await onCurrent(result);
      return result;
    },
    async upload(root, files, metadata, consent, onCurrent) {
      const current = enter(root);
      const attachments = [];
      for (const [index, file] of files.entries()) {
        const sha256 = await hashFile(file);
        if (!current()) return;
        attachments.push({
          client_id: `a${index + 1}`,
          filename: file.name,
          mime_type:
            file.type ||
            (file.name.toLowerCase().endsWith(".pdf")
              ? "application/pdf"
              : file.name.toLowerCase().endsWith(".png")
                ? "image/png"
                : "image/jpeg"),
          size_bytes: file.size,
          sha256,
        });
      }
      const fingerprint = JSON.stringify({ root, metadata, attachments });
      if (pending?.fingerprint !== fingerprint)
        pending = { fingerprint, key: makeKey(), startKey: makeKey() };
      const request = pending;
      const base = root + "/exam-diagnostics";
      let result = await api(base, {
        method: "POST",
        body: { ...metadata, attachments, idempotency_key: request.key },
      });
      if (!current()) return;
      if (result.status === "draft") {
        for (let index = 0; index < attachments.length; index++) {
          const attachment = result.attachments.find(
            (a) => a.client_id === attachments[index].client_id,
          );
          if (!attachment) throw new Error("服务端附件清单不完整，请重试");
          if (!attachment.received)
            await api(`${base}/${result.id}/attachments/${attachment.id}`, {
              method: "PUT",
              rawBody: files[index],
              headers: { "Content-Type": attachments[index].mime_type },
            });
          if (!current()) return;
        }
        result = await api(`${base}/${result.id}/start`, {
          method: "POST",
          body: { consent, idempotency_key: request.startKey },
        });
      }
      if (!current()) return;
      pending = null;
      await onCurrent(result);
      return result;
    },
    async poll(root, id, onCurrent) {
      const current = enter(root);
      if (removed.has(id)) return null;
      const result = await api(`${root}/exam-diagnostics/${id}`);
      if (current() && !removed.has(id)) await onCurrent(result);
      return current() && !removed.has(id) ? result : null;
    },
    async remove(root, diagnostic, onCurrent) {
      const current = enter(root);
      removed.add(diagnostic.id);
      try {
        await api(`${root}/exam-diagnostics/${diagnostic.id}`, {
          method: "DELETE",
        });
      } catch (error) {
        if (current()) removed.delete(diagnostic.id);
        throw error;
      }
      if (current()) await onCurrent();
    },
    async patch(root, id, questionId, changes, onCurrent) {
      const current = enter(root);
      const identity = JSON.stringify([root, id, questionId, changes]);
      if (!patches.has(identity)) patches.set(identity, makeKey());
      const result = await api(
        `${root}/exam-diagnostics/${id}/questions/${questionId}`,
        {
          method: "PATCH",
          body: { ...changes, idempotency_key: patches.get(identity) },
        },
      );
      if (current()) await onCurrent(result);
      return current() ? result : null;
    },
  };
}
