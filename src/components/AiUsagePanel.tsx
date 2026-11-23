import { useEffect, useState } from 'react';
import { api } from '../api';

type Usage = {
  today_calls: number; today_total_tokens: number; today_estimated_cny: string | null; seven_day_estimated_cny: string | null;
  average_assessment_cny: string | null; local_cache_hit_rate: number; mean_latency_ms: number; p95_latency_ms: number;
  price_note: string; days: Array<{ date: string; calls: number; total_tokens: number; estimated_cny: string | null }>;
  today_prompt_tokens?: number; today_cache_hit_tokens?: number; today_cache_miss_tokens?: number; today_output_tokens?: number;
  provider_success_rate?: number | null; failure_reasons?: Record<string, number>;
};
export const usageCost = (value: string | null) => value === null || !Number.isFinite(Number(value)) ? '未知' : `¥${Number(value).toFixed(6)}`;

export function AiUsagePanel() {
  const [value, setValue] = useState<Usage | null>(null); const [error, setError] = useState('');
  useEffect(() => { let active = true; void api<Usage>('/ai/usage').then((v) => { if (active) setValue(v); }).catch((e) => { if (active) setError(e instanceof Error ? e.message : '费用统计暂不可用'); }); return () => { active = false; }; }, []);
  return <section className="panel"><h2>AI用量与预估费用</h2><p className="helper-message">实际账单以DeepSeek为准；未获取usage的费用显示未知，不按0元处理。</p>
    {error && <p className="error" role="alert">{error}</p>}
    {!value && !error && <p>正在加载统计…</p>}
    {value && <p>今日输入 {value.today_prompt_tokens ?? 0}（官方缓存命中 {value.today_cache_hit_tokens ?? 0} / 未命中 {value.today_cache_miss_tokens ?? 0}），输出 {value.today_output_tokens ?? 0}。近7天API成功率：{value.provider_success_rate == null ? '尚无调用' : `${(value.provider_success_rate * 100).toFixed(1)}%`}。失败原因：{Object.entries(value.failure_reasons || {}).map(([code, count]) => `${code} ${count}次`).join('，') || '无'}。</p>}
    {value && <><dl><div><dt>今日调用 / Token</dt><dd>{value.today_calls} / {value.today_total_tokens}</dd></div><div><dt>今日预估 / 近7天预估</dt><dd>{usageCost(value.today_estimated_cny)} / {usageCost(value.seven_day_estimated_cny)}</dd></div><div><dt>平均完成稿费用</dt><dd>{usageCost(value.average_assessment_cny)}</dd></div><div><dt>本地缓存命中率</dt><dd>{(value.local_cache_hit_rate * 100).toFixed(1)}%</dd></div><div><dt>API平均 / P95耗时</dt><dd>{(value.mean_latency_ms / 1000).toFixed(2)}秒 / {(value.p95_latency_ms / 1000).toFixed(2)}秒</dd></div></dl><p className="helper-message">{value.price_note}</p></>}
  </section>;
}
