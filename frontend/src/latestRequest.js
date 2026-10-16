// A newer read or a context change makes every earlier response obsolete.
export function createLatestRequest() {
  let generation = 0;
  return {
    checkpoint() {
      const current = generation;
      return () => current === generation;
    },
    invalidate() {
      generation += 1;
    },
    async run(load, publish) {
      const current = ++generation;
      try {
        const result = await load();
        if (current !== generation) return false;
        publish(result);
        return true;
      } catch (error) {
        if (current === generation) throw error;
        return false;
      }
    },
  };
}
