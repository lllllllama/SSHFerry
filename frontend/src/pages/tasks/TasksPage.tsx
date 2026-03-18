import { Navigate } from 'react-router-dom';

import { AppTopBar } from '../../components/layout/AppTopBar';
import { TaskCenter } from '../../components/tasks/TaskCenter';
import { useAuthStore } from '../../store/auth';

export function TasksPage() {
  const status = useAuthStore((state) => state.status);

  if (status === 'error') {
    return <Navigate to="/" replace />;
  }

  return (
    <main className="app-shell">
      <AppTopBar />
      <section className="tasks-page-shell">
        <TaskCenter fullPage />
      </section>
    </main>
  );
}
