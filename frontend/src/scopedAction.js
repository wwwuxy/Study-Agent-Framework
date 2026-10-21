// Prevent duplicate mutations and publishing results into another account/space.
export function createScopedAction() {
  let generation = 0,
    pending = null;
  return {
    invalidate() {
      generation += 1;
      pending = null;
    },
    run(load, publish) {
      if (pending) return pending;
      const ticket = generation;
      let request;
      try {
        request = load();
      } catch (error) {
        return Promise.reject(error);
      }
      pending = (async () => {
        try {
          const result = await request;
          if (ticket === generation) await publish(result);
          return result;
        } catch (error) {
          if (ticket === generation) throw error;
        } finally {
          if (ticket === generation) pending = null;
        }
      })();
      return pending;
    },
  };
}
