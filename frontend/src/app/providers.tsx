import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';

import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { ToastViewport } from '../components/common/ToastViewport';
import { useBackendSession } from '../hooks/useBackendSession';
import { useLogSocket } from '../hooks/useLogSocket';
import { useTaskSocket } from '../hooks/useTaskSocket';
import { useWorkspaceBootstrap } from '../hooks/useWorkspaceBootstrap';
import { I18nProvider } from '../i18n';
import { router } from './router';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
});

function AppRuntime() {
  useBackendSession();
  useWorkspaceBootstrap();
  useTaskSocket();
  useLogSocket();
  return null;
}

export function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AppRuntime />
        <RouterProvider router={router} />
        <ConfirmDialog />
        <ToastViewport />
      </I18nProvider>
    </QueryClientProvider>
  );
}