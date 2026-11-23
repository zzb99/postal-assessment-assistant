import { deviceToken } from './platform/services';

App({
  onLaunch() {
    // 提前生成本机凭证，首次打开填报页时不用再等待。
    deviceToken().catch(() => undefined);
    // 内部工具频繁更新：有新版本时提示重启，避免职工继续用旧流程出单。
    if (typeof wx.getUpdateManager !== 'function') return;
    const manager = wx.getUpdateManager();
    manager.onUpdateReady(() => {
      wx.showModal({
        title: '发现新版本',
        content: '新版本已准备好，重启后使用。未生成的填写内容会保留。',
        showCancel: false,
        confirmText: '立即重启',
        success: () => manager.applyUpdate(),
      });
    });
  },
});
