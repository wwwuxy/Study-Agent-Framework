export const shouldSend = (e) =>
  e.key === "Enter" &&
  !!(e.ctrlKey || e.metaKey) &&
  !e.isComposing &&
  !e.nativeEvent?.isComposing;

export function createPlanningChatState(makeKey = () => crypto.randomUUID()) {
  let generation = 0,
    pending = null,
    last = null;
  return {
    invalidate() {
      generation++;
      pending = null;
      last = null;
    },
    recover(row) {
      last = { content: row.content, key: row.idempotency_key };
    },
    runSend(content, load, publish, retry = false) {
      if (pending) return pending;
      const ticket = generation;
      if (!retry || !last || last.content !== content)
        last = { content, key: makeKey() };
      const body = { content, idempotency_key: last.key, retry };
      let response;
      try {
        response = load(body);
      } catch (e) {
        return Promise.reject(e);
      }
      pending = (async () => {
        try {
          const result = await response;
          if (ticket === generation) await publish(result);
          return result;
        } catch (e) {
          if (ticket === generation) throw e;
        } finally {
          if (ticket === generation) pending = null;
        }
      })();
      return pending;
    },
  };
}
