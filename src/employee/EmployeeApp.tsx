import { useEffect, useMemo, useState } from 'react';
import { FillPage } from './FillPage';
import { RecordsPage } from './RecordsPage';
import { ResultPage } from './ResultPage';
import { fillController } from './platform';
import './employee.css';

export type Route = { name: 'fill' } | { name: 'records' } | { name: 'result'; id: number; fresh: boolean };

/** 职工端使用 hash 路由，静态部署无需额外的服务器规则：#/、#/records、#/result/123。 */
export function parseRoute(hash: string): Route {
  const result = /^#\/result\/(\d+)(\?fresh)?$/.exec(hash);
  if (result) return { name: 'result', id: Number(result[1]), fresh: Boolean(result[2]) };
  if (/^#\/records\/?$/.test(hash)) return { name: 'records' };
  return { name: 'fill' };
}

const currentHash = () => (typeof window === 'undefined' ? '' : window.location.hash);

/** 职工免登录网页版：与微信小程序共用填报流程（miniprogram/src/shared）。 */
export default function EmployeeApp() {
  const [route, setRoute] = useState<Route>(() => parseRoute(currentHash()));
  const controller = useMemo(() => fillController(), []);

  useEffect(() => {
    const update = () => {
      setRoute(parseRoute(currentHash()));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);

  return (
    <div className="emp">
      <header className="emp-header">
        <div className="emp-header-row">
          <a className="emp-brand" href="#/"><span aria-hidden="true">邮</span>通信生产考核</a>
          <a className="emp-admin" href="/admin">后台管理</a>
        </div>
        <nav className="emp-tabs" aria-label="职工填报">
          <a href="#/" aria-current={route.name === 'fill' ? 'page' : undefined} className={route.name === 'fill' ? 'on' : ''}>填写考核单</a>
          <a href="#/records" aria-current={route.name !== 'fill' ? 'page' : undefined} className={route.name !== 'fill' ? 'on' : ''}>我的记录</a>
        </nav>
      </header>
      <main className="emp-main">
        {route.name === 'fill' && <FillPage controller={controller} />}
        {route.name === 'records' && <RecordsPage />}
        {route.name === 'result' && <ResultPage key={route.id} id={route.id} fresh={route.fresh} />}
      </main>
    </div>
  );
}
