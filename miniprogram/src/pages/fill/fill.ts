import { fillController, rememberRecords } from '../../platform/services';
import { changedPaths, toast } from '../../platform/wx';
import type { FillController } from '../../shared/controller';
import type { EditableField, FillState, FillView } from '../../shared/fill';
import type { QuickUnit } from '../../shared/types';

type Dataset = Record<string, string>;
type ValueEvent = { detail: { value: string | number }; currentTarget: { dataset: Dataset } };
type TapEvent = { currentTarget: { dataset: Dataset } };

let controller: FillController | null = null;
let unsubscribe: (() => void) | null = null;
let lastComposition: unknown = null;

Page({
  data: {
    ready: false,
    fatal: '',
    state: null as FillState | null,
    view: null as FillView | null,
    units: [] as QuickUnit[],
    storageOk: true,
    locked: false,
    quantityAnswer: '',
    rulesExpanded: false,
  },

  async onLoad() {
    try {
      controller = await fillController();
    } catch (error) {
      this.setData({ fatal: error instanceof Error ? error.message : '初始化失败，请重新打开小程序。' });
      return;
    }
    if (unsubscribe) unsubscribe();
    unsubscribe = controller.subscribe(() => this.render());
    this.render();
    await controller.loadConfig();
  },

  onShow() {
    if (!controller) return;
    if (!controller.getSnapshot().config) void controller.loadConfig();
    this.render();
  },

  onUnload() {
    if (unsubscribe) unsubscribe();
    unsubscribe = null;
  },

  render() {
    if (!controller) return;
    const { state, view, config, storageOk } = controller.getSnapshot();
    const previous = this.data.state;
    const changes: Record<string, unknown> = {};
    if (!previous) {
      changes.state = state;
    } else {
      // 输入值也同步回视图数据（与官方示例一致），之后重置、清空时视图才会真正更新输入框。
      const { form, ...rest } = state;
      const { form: previousForm, ...previousRest } = previous;
      Object.assign(changes, changedPaths(previousRest, rest, 'state'));
      Object.assign(changes, changedPaths(previousForm, form, 'state.form'));
    }
    Object.assign(changes, changedPaths(this.data.view as Record<string, unknown> | null, view as unknown as Record<string, unknown>, 'view'));
    const units = config ? config.units : [];
    if (JSON.stringify(units) !== JSON.stringify(this.data.units)) changes.units = units;
    const locked = state.aiPending || state.submitting;
    if (locked !== this.data.locked) changes.locked = locked;
    if (state.composition !== lastComposition) {
      lastComposition = state.composition;
      changes.rulesExpanded = view.rulesOpen;
    }
    if (storageOk !== this.data.storageOk) changes.storageOk = storageOk;
    if (!this.data.ready) changes.ready = true;
    if (Object.keys(changes).length) this.setData(changes);
  },

  onInput(event: ValueEvent) {
    if (!controller) return;
    controller.setField(event.currentTarget.dataset.key as EditableField, String(event.detail.value));
  },

  onDate(event: ValueEvent) {
    if (controller) controller.setField('incident_date', String(event.detail.value));
  },

  onShift(event: TapEvent) {
    if (controller && !this.data.locked) controller.setField('shift', event.currentTarget.dataset.value);
  },

  onUnit(event: ValueEvent) {
    const unit = this.data.units[Number(event.detail.value)];
    if (controller && unit) controller.setField('unit', String(unit.id));
  },

  toggleMode() {
    if (!controller) return;
    const { state } = controller.getSnapshot();
    controller.setMode(state.mode === 'ai' ? 'manual' : 'ai');
  },

  toggleConfirm() {
    if (!controller) return;
    const { state, view } = controller.getSnapshot();
    if (view.confirmVisible && !state.aiPending && !state.submitting) controller.confirm(!state.editConfirmed);
  },

  compose() {
    if (controller) void controller.compose();
  },

  answerBoolean(event: TapEvent) {
    if (!controller) return;
    const question = controller.getSnapshot().view.question;
    if (question) void controller.answer(question, event.currentTarget.dataset.value === 'yes');
  },

  onQuantityAnswer(event: ValueEvent) {
    this.setData({ quantityAnswer: String(event.detail.value) });
  },

  answerQuantity() {
    if (!controller) return;
    const question = controller.getSnapshot().view.question;
    if (!question) return;
    void controller.answer(question, Number(this.data.quantityAnswer));
    this.setData({ quantityAnswer: '' });
  },

  choose(event: TapEvent) {
    const { rule, option } = event.currentTarget.dataset;
    if (controller) void controller.choose(rule, option);
  },

  toggleRules() {
    if (controller) controller.toggleRules();
  },

  toggleRulesOpen() {
    this.setData({ rulesExpanded: !this.data.rulesExpanded });
  },

  retryConfig() {
    if (controller && !controller.getSnapshot().config) void controller.loadConfig();
  },

  async submit() {
    if (!controller) return;
    const record = await controller.submit();
    if (record) {
      rememberRecords([record]);
      wx.navigateTo({ url: `/pages/result/result?id=${record.id}&fresh=1` });
      return;
    }
    const message = controller.getSnapshot().state.error;
    if (message) toast(message);
  },

  onShareAppMessage() {
    return { title: '通信生产考核 · 免登录填报', path: '/pages/fill/fill' };
  },
});
