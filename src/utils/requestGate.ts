/** A response may write state only while its session/request generation is current. */
export function createRequestGate() {
  let generation = 0;
  return {
    capture: () => generation,
    invalidate: () => ++generation,
    isCurrent: (token: number) => token === generation,
  };
}
