import type { AssessmentForm } from '../types';

export const DRAFT_KEY = 'postal-assessment-draft-v2';
export function loadDraft(fallback: AssessmentForm, storage: Storage | undefined = typeof localStorage === 'undefined' ? undefined : localStorage): AssessmentForm {
  try {
    if (!storage) return fallback;
    const draft = { ...fallback, ...JSON.parse(storage.getItem(DRAFT_KEY) || '{}') } as AssessmentForm;
    // Migrate v1 drafts that stored "一班张三" as one field.
    const match = draft.inspector.match(/^(一班|二班|三班)(.+)$/);
    if (match) { draft.team = match[1]; draft.inspector = match[2]; }
    return draft;
  } catch { return fallback; }
}
export function saveDraft(form: AssessmentForm, storage: Storage | undefined = typeof localStorage === 'undefined' ? undefined : localStorage) {
  try { storage?.setItem(DRAFT_KEY, JSON.stringify(form)); } catch { /* storage may be unavailable */ }
}
export function clearDraft(storage: Storage | undefined = typeof localStorage === 'undefined' ? undefined : localStorage) {
  try { storage?.removeItem(DRAFT_KEY); } catch { /* storage may be unavailable */ }
}
