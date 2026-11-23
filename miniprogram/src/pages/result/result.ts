import { cachedRecord, documentFile, findRecord } from '../../platform/services';
import { cancelled, toast } from '../../platform/wx';
import { documentFileName, formatMoney, shareText, statusLabel } from '../../shared/format';
import type { QuickRecord } from '../../shared/types';

/** 当前展示的记录；页面切换后迟到的下载结果不能写到新页面上。 */
let current: QuickRecord | null = null;

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

Page({
  data: {
    loading: true,
    error: '',
    fresh: false,
    record: null as QuickRecord | null,
    amountText: '',
    statusText: '',
    effective: false,
    imagePath: '',
    pdfPath: '',
    preparing: false,
    hint: '',
  },

  async onLoad(query: Record<string, string | undefined>) {
    const id = Number(query.id);
    const fresh = query.fresh === '1';
    this.setData({ fresh });
    if (fresh) wx.setNavigationBarTitle({ title: '考核单已生成' });
    let record = Number.isInteger(id) && id > 0 ? cachedRecord(id) : null;
    if (!record && Number.isInteger(id) && id > 0) {
      try {
        record = await findRecord(id);
      } catch (error) {
        this.setData({ loading: false, error: messageOf(error, '读取失败，请稍后重试。') });
        return;
      }
    }
    if (!record) {
      this.setData({ loading: false, error: '本机找不到这张考核单。' });
      return;
    }
    current = record;
    const effective = record.status === 'effective';
    this.setData({ loading: false, record, amountText: formatMoney(record.penalty_amount), statusText: statusLabel(record.status), effective });
    if (effective) void this.prepare();
  },

  onUnload() {
    current = null;
  },

  /** 先准备好图片和 PDF，用户点击分享时直接调起微信，不再等待下载。 */
  async prepare() {
    const record = current;
    if (!record || this.data.preparing) return;
    this.setData({ preparing: true, hint: '正在准备文书图片和 PDF…' });
    const image = documentFile(record, 'png').then((imagePath) => { if (current === record) this.setData({ imagePath }); });
    const pdf = documentFile(record, 'pdf').then((pdfPath) => { if (current === record) this.setData({ pdfPath }); });
    try {
      await Promise.all([image, pdf]);
      if (current === record) this.setData({ preparing: false, hint: '' });
    } catch (error) {
      await Promise.all([image.catch(() => undefined), pdf.catch(() => undefined)]);
      if (current === record) this.setData({ preparing: false, hint: `${messageOf(error, '文书下载失败')}，可点「重新加载文书」再试。` });
    }
  },

  shareImage() {
    if (!this.data.imagePath) return;
    wx.showShareImageMenu({
      path: this.data.imagePath,
      fail: (error) => { if (!cancelled(error)) toast('无法打开分享，请长按下方图片发送。'); },
    });
  },

  shareFile() {
    const record = current;
    if (!record || !this.data.pdfPath) return;
    wx.shareFileMessage({
      filePath: this.data.pdfPath,
      fileName: documentFileName(record, 'pdf'),
      fail: (error) => { if (!cancelled(error)) toast('当前微信不支持直接发文件，请点「打开 PDF」后用右上角转发。'); },
    });
  },

  previewImage() {
    if (this.data.imagePath) wx.previewImage({ urls: [this.data.imagePath], current: this.data.imagePath });
  },

  openPdf() {
    if (!this.data.pdfPath) return;
    wx.openDocument({ filePath: this.data.pdfPath, fileType: 'pdf', showMenu: true, fail: () => toast('无法打开 PDF，请稍后重试。') });
  },

  async openWord() {
    const record = current;
    if (!record) return;
    wx.showLoading({ title: '正在打开 Word', mask: true });
    try {
      const filePath = await documentFile(record, 'word');
      wx.hideLoading();
      wx.openDocument({ filePath, fileType: 'docx', showMenu: true, fail: () => toast('无法打开 Word，请稍后重试。') });
    } catch (error) {
      wx.hideLoading();
      toast(messageOf(error, 'Word 下载失败，请重试。'));
    }
  },

  copyText() {
    const record = current;
    if (!record) return;
    wx.setClipboardData({ data: shareText(record), success: () => toast('文字已复制，可粘贴到群里。') });
  },

  next() {
    wx.switchTab({ url: '/pages/fill/fill' });
  },

  onShareAppMessage() {
    return { title: '通信生产考核 · 免登录填报', path: '/pages/fill/fill' };
  },
});
