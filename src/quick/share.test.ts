import { describe, expect, it, vi } from 'vitest';
import { sharePreparedFile } from './share';

describe('手机分享必须由点击直接触发', () => {
  it('分享预先准备的文件，不先发网络请求', async () => {
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    const share = vi.fn().mockResolvedValue(undefined);
    expect(await sharePreparedFile(file, { share, canShare: () => true })).toBe('shared');
    expect(share).toHaveBeenCalledWith({ files: [file], title: 'test.pdf' });
  });
  it('不支持、用户取消、其他错误分别处理', async () => {
    const file = new File(['test'], 'test.pdf');
    expect(await sharePreparedFile(file, {})).toBe('unsupported');
    expect(await sharePreparedFile(file, { share: vi.fn(), canShare: () => false })).toBe('unsupported');
    expect(await sharePreparedFile(file, { share: vi.fn().mockRejectedValue(new DOMException('cancel', 'AbortError')), canShare: () => true })).toBe('cancelled');
    await expect(sharePreparedFile(file, { share: vi.fn().mockRejectedValue(new Error('blocked')), canShare: () => true })).rejects.toThrow('blocked');
  });
});
