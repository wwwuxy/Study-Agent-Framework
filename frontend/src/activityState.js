export function createActivityActions() {
  let generation = 0;
  const keys = new Map(),
    pending = new Map();
  return {
    invalidate() {
      generation++;
      pending.clear();
      keys.clear();
    },
    checkpoint() {
      const version = generation;
      return () => version === generation;
    },
    run(name, operation) {
      if (pending.has(name)) return pending.get(name);
      const version = generation;
      if (!keys.has(name)) keys.set(name, crypto.randomUUID());
      const request = Promise.resolve(
        operation({ idempotency_key: keys.get(name) }),
      )
        .then((value) => ({ value, current: version === generation }))
        .finally(() => {
          if (version === generation) pending.delete(name);
        });
      pending.set(name, request);
      return request;
    },
  };
}
