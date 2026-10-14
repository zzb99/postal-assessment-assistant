const KEY = 'assessment-quick-unfinished-v1';
const fields = ['incident_date', 'shift', 'unit', 'facts', 'assessment_content', 'quantity', 'penalty_amount'] as const;
export function readDraft(): Record<string, string> {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(KEY) || '{}');
    if (!data || typeof data !== 'object') return {};
    return Object.fromEntries(fields.flatMap((key) => {
      const value = (data as Record<string, unknown>)[key];
      return typeof value === 'string' && value.length <= 1000 ? [[key, value]] : [];
    }));
  } catch { return {}; }
}
export function saveDraft(data: Record<string, string>): boolean {
  try { localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(fields.map((key) => [key, data[key] || ''])))); return true; }
  catch { return false; }
}
export function clearDraft(): void {
  try { localStorage.removeItem(KEY); } catch { /* The UI still starts a new notice. */ }
}

// Short-lived, tab-scoped copy of a server-signed AI proposal. Never put tokens
// in persistent localStorage; the server verifies expiration and policy digest.
const PROPOSAL_KEY = 'assessment-quick-proposal-session-v1';
const context = (data: Record<string, string>) =>
  JSON.stringify(['incident_date', 'shift', 'unit', 'facts', 'quantity', 'penalty_amount'].map((k) => data[k] || ''));
export function saveSessionProposal(data: Record<string, string>, original: string): void {
  try {
    if (!data.ai_proposal) { sessionStorage.removeItem(PROPOSAL_KEY); return; }
    sessionStorage.setItem(PROPOSAL_KEY, JSON.stringify({ context: context(data), token: data.ai_proposal,
      signedContent: original, expires: Date.now() + 45 * 60_000 }));
  } catch { /* Permission denied: continue as a plain local draft. */ }
}
export function readSessionProposal(data: Record<string, string>): { token: string; signedContent: string } | null {
  try {
    const raw: unknown = JSON.parse(sessionStorage.getItem(PROPOSAL_KEY) || 'null');
    if (!raw || typeof raw !== 'object') return null;
    const item = raw as Record<string, unknown>;
    if (item.context !== context(data) || typeof item.expires !== 'number' || Date.now() > item.expires ||
        typeof item.token !== 'string' || typeof item.signedContent !== 'string') return null;
    return { token: item.token, signedContent: item.signedContent };
  } catch { return null; }
}
export function clearSessionProposal(): void {
  try { sessionStorage.removeItem(PROPOSAL_KEY); } catch { /* Storage may be unavailable. */ }
}
