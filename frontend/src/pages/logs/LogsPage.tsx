import { Navigate } from 'react-router-dom';

import { AppTopBar } from '../../components/layout/AppTopBar';
import { LogPlaceholder } from '../../components/logs/LogPlaceholder';
import { useAuthStore } from '../../store/auth';

export function LogsPage() {
  const status = useAuthStore((state) => state.status);

  if (status === 'error') {
    return <Navigate to="/" replace />;
  }

  return (
    <main className="app-shell">
      <AppTopBar />
      <section className="content-page-shell logs-page-shell">
        <LogPlaceholder fullPage />
      </section>
    </main>
  );
}