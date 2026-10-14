import type { AssessmentForm } from '../types';

export const DRAFT_KEY = 'postal-assessment-draft-v2';
export function loadDraft(fallback: AssessmentForm, storage: Storage | undefined = typeof localStorage === 'undefined' ? undefined : localStorage): AssessmentForm {
  try { return storage ? { ...fallback, ...JSON.parse(storage.getItem(DRAFT_KEY) || '{}') } : fallback; } catch { return fallback; }
}
export function saveDraft(form: AssessmentForm, storage: Storage | undefined = typeof localStorage === 'undefined' ? undefined : localStorage) {
  try { storage?.setItem(DRAFT_KEY, JSON.stringify(form)); } catch { /* storage may be unavailable */ }
}
export function clearDraft(storage: Storage | undefined = typeof localStorage === 'undefined' ? undefined : localStorage) {
  try { storage?.removeItem(DRAFT_KEY); } catch { /* storage may be unavailable */ }
}
