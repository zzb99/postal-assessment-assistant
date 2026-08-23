export type Role = 'admin' | 'leader' | 'department_manager';

export type CurrentUser = { id: number; username: string; display_name: string; role: Role; department_id: number | null };
export type ReferenceData = {
  departments: Array<{ id: number; name: string }>;
  units: Array<{ id: number; name: string; department_id: number | null }>;
  categories: Array<{ id: number; name: string }>;
  shifts: string[];
  operation_stages: string[];
};
export type Assessment = {
  id: number; assessment_no: string | null; incident_date: string; shift: string;
  assessment_unit_id: number | null; assessment_unit_name_snapshot: string;
  department_id: number | null; department_name_snapshot: string | null;
  inspector_name: string; assessment_content: string; category_id: number | null;
  category_name_snapshot: string | null; operation_stage: string | null; regulation_version: string | null;
  penalty_amount: string; penalty_amount_cn: string; remark: string | null; status: 'draft' | 'effective' | 'voided';
  created_by: number; created_at: string; updated_at: string; finalized_at: string | null; voided_at: string | null; void_reason: string | null;
};
export type AssessmentPage = { items: Assessment[]; total: number; page: number; page_size: number };
export type Overview = { month_count: number; month_amount: string; year_count: number; year_amount: string; unit_count: number };
export type GroupStatistic = { name: string; count: number; amount: string };
export type ManagedUser = CurrentUser & { active: boolean };
export type CatalogItem = { id: number; name: string; active: boolean; department_id?: number | null; kind?: string; sort_order?: number };
export type ManagementCatalog = { departments: CatalogItem[]; units: CatalogItem[]; categories: CatalogItem[]; master_items: CatalogItem[] };

const TOKEN_KEY = 'assessment-access-token';
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) clearToken();
    throw new Error(body.detail || '请求失败，请稍后重试。');
  }
  return response.json() as Promise<T>;
}

export async function download(path: string, filename: string): Promise<void> {
  const headers = new Headers({ Authorization: `Bearer ${getToken() || ''}` });
  const response = await fetch(`/api${path}`, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || '文件生成失败。');
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}
