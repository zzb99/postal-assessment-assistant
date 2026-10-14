import type { Assessment } from '../api';

export function mergeRecent(current: Assessment[], incoming: Assessment[]): Assessment[] {
  const byId = new Map<number, Assessment>();
  for (const item of [...current, ...incoming]) {
    const previous = byId.get(item.id);
    if (!previous || Date.parse(item.updated_at) > Date.parse(previous.updated_at)) byId.set(item.id, item);
  }
  return [...byId.values()].sort((a, b) => b.id - a.id).slice(0, 10);
}
