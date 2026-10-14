import { useEffect, useState } from 'react';
import App from './App';
import QuickPage from './quick/QuickPage';

export default function Portal() {
  const [management, setManagement] = useState(() => window.location.hash === '#manage');
  useEffect(() => { const update = () => setManagement(window.location.hash === '#manage'); window.addEventListener('hashchange', update); return () => window.removeEventListener('hashchange', update); }, []);
  return management ? <><div className="management-entry"><a href="#">返回职工填报</a></div><App /></> : <QuickPage />;
}
