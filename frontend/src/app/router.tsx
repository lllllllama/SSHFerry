import { createBrowserRouter, Navigate } from 'react-router-dom';

import { BootstrapPage } from '../pages/bootstrap/BootstrapPage';
import { LogsPage } from '../pages/logs/LogsPage';
import { TasksPage } from '../pages/tasks/TasksPage';
import { WorkspacePage } from '../pages/workspace/WorkspacePage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <BootstrapPage />,
  },
  {
    path: '/workspace',
    element: <WorkspacePage />,
  },
  {
    path: '/tasks',
    element: <TasksPage />,
  },
  {
    path: '/logs',
    element: <LogsPage />,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);