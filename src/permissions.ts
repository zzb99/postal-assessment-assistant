export type Page = 'home' | 'create' | 'policy' | 'ledger' | 'statistics' | 'management';

export const roleName = (role: string) => ({ admin: '系统管理员', leader: '领导（只读）', department_manager: '主管', employee: '职工' }[role] || '未知角色');

export function getPermissions(role: string) {
  const supervisor = role === 'admin' || role === 'department_manager';
  const employee = role === 'employee';
  const reader = role === 'leader';
  return {
    create: supervisor || employee,
    finalize: supervisor,
    void: supervisor,
    export: supervisor || reader,
    statistics: supervisor || reader,
    manage: role === 'admin',
  };
}

export function navigationFor(role: string): Array<{ id: Page; label: string }> {
  if (!['admin', 'department_manager', 'employee', 'leader'].includes(role)) return [];
  const permissions = getPermissions(role);
  return [
    { id: 'home', label: '工作台' },
    ...(permissions.create ? [{ id: 'create' as const, label: role === 'employee' ? '新建填报' : '新建考核' }] : []),
    { id: 'ledger', label: role === 'employee' ? '我的记录' : '考核台账' },
    { id: 'policy', label: '制度查询' },
    ...(permissions.statistics ? [{ id: 'statistics' as const, label: '统计分析' }] : []),
    ...(permissions.manage ? [{ id: 'management' as const, label: '系统管理' }] : []),
  ];
}
