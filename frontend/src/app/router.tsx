import { createBrowserRouter, Navigate } from 'react-router-dom';

import { BootstrapPage } from '../pages/bootstrap/BootstrapPage';
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
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
