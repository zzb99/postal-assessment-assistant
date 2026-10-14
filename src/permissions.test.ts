import { describe, expect, it } from 'vitest';
import { getPermissions, navigationFor, roleName } from './permissions';

describe('主管与职工功能边界', () => {
  it('职工只有日常填报、本人记录和制度入口', () => {
    expect(navigationFor('employee').map((item) => item.id)).toEqual(['home', 'create', 'ledger', 'policy']);
    expect(getPermissions('employee')).toMatchObject({ create: true, finalize: false, void: false, export: false, statistics: false, manage: false });
    expect(roleName('employee')).toBe('职工');
  });
  it('主管复核本部门数据，管理员保留系统管理', () => {
    expect(getPermissions('department_manager')).toMatchObject({ finalize: true, void: true, export: true, statistics: true, manage: false });
    expect(navigationFor('department_manager').some((item) => item.id === 'management')).toBe(false);
    expect(navigationFor('admin').some((item) => item.id === 'management')).toBe(true);
    expect(roleName('department_manager')).toBe('主管');
  });
  it('保留历史领导只读权限，未知角色默认拒绝', () => {
    expect(getPermissions('leader')).toMatchObject({ create: false, finalize: false, void: false });
    expect(navigationFor('leader').some((item) => item.id === 'create')).toBe(false);
    expect(Object.values(getPermissions('unknown')).every((value) => value === false)).toBe(true);
    expect(navigationFor('unknown')).toEqual([]);
  });
});
