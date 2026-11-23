import { lazy, Suspense, useEffect, useState } from 'react';

// 两个入口分开打包：职工手机端不下载管理后台代码，管理后台也不加载职工端样式。
const AdminApp = lazy(() => import('./App'));
const EmployeeApp = lazy(() => import('./employee/EmployeeApp'));

/** 管理网站：/admin（旧地址 #manage 继续有效），需要账号登录；其他地址都是职工免登录填报。 */
export function isManagement(location: Pick<Location, 'pathname' | 'hash'>): boolean {
  return location.hash === '#manage' || /^\/admin(\/|$)/.test(location.pathname);
}

const loading = <div style={{ padding: 32, textAlign: 'center', color: '#5f6e66' }}>正在打开…</div>;

export default function Portal() {
  const [management, setManagement] = useState(() => isManagement(window.location));
  useEffect(() => {
    const update = () => setManagement(isManagement(window.location));
    window.addEventListener('hashchange', update);
    window.addEventListener('popstate', update);
    return () => {
      window.removeEventListener('hashchange', update);
      window.removeEventListener('popstate', update);
    };
  }, []);
  return (
    <Suspense fallback={loading}>
      {management ? <><div className="management-entry"><a href="/">返回职工填报</a></div><AdminApp /></> : <EmployeeApp />}
    </Suspense>
  );
}
