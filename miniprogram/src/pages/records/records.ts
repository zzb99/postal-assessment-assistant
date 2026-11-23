import { loadRecords } from '../../platform/services';
import { toast } from '../../platform/wx';
import { formatMoney, mergeRecent, statusLabel } from '../../shared/format';
import type { QuickRecord } from '../../shared/types';

type Row = { id: number; no: string; unit: string; meta: string; amount: string; status: string; statusClass: string };

const toRow = (record: QuickRecord): Row => ({
  id: record.id,
  no: record.assessment_no || `未生成 #${record.id}`,
  unit: record.assessment_unit_name_snapshot,
  meta: `${record.incident_date} ${record.shift} · ${record.team} ${record.inspector_name}`,
  amount: `¥${formatMoney(record.penalty_amount)}`,
  status: statusLabel(record.status),
  statusClass: `status-${record.status}`,
});

let items: QuickRecord[] = [];
let page = 0;
let busy = false;

function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '读取失败，请稍后重试。';
}

Page({
  data: {
    rows: [] as Row[],
    total: 0,
    loading: true,
    error: '',
    done: false,
  },

  onShow() {
    void this.refresh();
  },

  async onPullDownRefresh() {
    await this.refresh();
    wx.stopPullDownRefresh();
  },

  async refresh() {
    if (busy) return;
    busy = true;
    this.setData({ loading: !this.data.rows.length, error: '' });
    try {
      const result = await loadRecords(1);
      items = result.items;
      page = 1;
      this.setData({ rows: items.map(toRow), total: result.total, loading: false, done: result.items.length < result.page_size || items.length >= result.total });
    } catch (error) {
      this.setData({ loading: false, error: messageOf(error) });
    } finally {
      busy = false;
    }
  },

  async onReachBottom() {
    if (busy || this.data.done) return;
    busy = true;
    try {
      const result = await loadRecords(page + 1);
      page += 1;
      items = mergeRecent(items, result.items, 1000);
      this.setData({ rows: items.map(toRow), total: result.total, done: result.items.length < result.page_size || items.length >= result.total });
    } catch (error) {
      toast(messageOf(error));
    } finally {
      busy = false;
    }
  },

  open(event: { currentTarget: { dataset: { id: number | string } } }) {
    wx.navigateTo({ url: `/pages/result/result?id=${event.currentTarget.dataset.id}` });
  },

  goFill() {
    wx.switchTab({ url: '/pages/fill/fill' });
  },

  onShareAppMessage() {
    return { title: '通信生产考核 · 免登录填报', path: '/pages/fill/fill' };
  },
});
