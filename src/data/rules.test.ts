import { describe, expect, it, vi } from 'vitest';
vi.mock('../api', () => ({ api: vi.fn() }));
import { api } from '../api';
import { loadRules } from './rules';

describe('policy access is authenticated for every session', () => {
  it('does not return a former manager session catalog to another session', async () => {
    vi.mocked(api).mockResolvedValueOnce({ rules: [{ id: 'one', stage: '卸车', clause: '第1条', pricingOptions: [] }] });
    expect((await loadRules())[0].id).toBe('one');
    vi.mocked(api).mockRejectedValueOnce(new Error('无权限'));
    await expect(loadRules()).rejects.toThrow('无权限');
    expect(api).toHaveBeenCalledTimes(2);
  });
});
