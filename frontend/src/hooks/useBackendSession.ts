import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { getAuthSession, getHealth } from '../api/auth';
import { getErrorMessage } from '../api/http';
import { useAuthStore } from '../store/auth';

export function useBackendSession() {
  const status = useAuthStore((state) => state.status);
  const setLoading = useAuthStore((state) => state.setLoading);
  const setBackendSession = useAuthStore((state) => state.setBackendSession);
  const setInitError = useAuthStore((state) => state.setInitError);

  const query = useQuery({
    queryKey: ['backend-session'],
    queryFn: async () => {
      const health = await getHealth();
      if (!health.ready) {
        throw new Error(health.startup_error || '本地后端尚未完成启动。');
      }
      const session = await getAuthSession();
      return { health, session };
    },
    retry: 1,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
  });

  useEffect(() => {
    if (query.isPending && status !== 'ready') {
      setLoading();
    }
  }, [query.isPending, setLoading, status]);

  useEffect(() => {
    if (!query.data) {
      return;
    }
    setBackendSession(query.data);
  }, [query.data, setBackendSession]);

  useEffect(() => {
    if (!query.error) {
      return;
    }
    setInitError(getErrorMessage(query.error, '初始化失败'));
  }, [query.error, setInitError]);

  return query;
}
