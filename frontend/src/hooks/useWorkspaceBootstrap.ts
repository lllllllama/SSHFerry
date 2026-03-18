import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { listLocalDrives } from '../api/localFiles';
import { listSessions } from '../api/sessions';
import { listSites } from '../api/sites';
import { useAuthStore } from '../store/auth';
import { useWorkspaceStore } from '../store/workspace';

export function useWorkspaceBootstrap() {
  const authReady = useAuthStore((state) => state.status === 'ready');
  const selectedSiteName = useWorkspaceStore((state) => state.selectedSiteName);
  const localCurrentPath = useWorkspaceStore((state) => state.localCurrentPath);
  const setSelectedSiteName = useWorkspaceStore((state) => state.setSelectedSiteName);
  const setLocalPath = useWorkspaceStore((state) => state.setLocalPath);
  const syncSessions = useWorkspaceStore((state) => state.syncSessions);

  const sitesQuery = useQuery({
    queryKey: ['sites'],
    queryFn: listSites,
    enabled: authReady,
    staleTime: 15000,
  });

  const sessionsQuery = useQuery({
    queryKey: ['sessions'],
    queryFn: listSessions,
    enabled: authReady,
    staleTime: 5000,
  });

  const drivesQuery = useQuery({
    queryKey: ['local-drives'],
    queryFn: listLocalDrives,
    enabled: authReady,
    staleTime: 60000,
  });

  useEffect(() => {
    if (!sitesQuery.data?.items.length) {
      return;
    }
    if (!selectedSiteName) {
      setSelectedSiteName(sitesQuery.data.items[0].name);
    }
  }, [selectedSiteName, setSelectedSiteName, sitesQuery.data?.items]);

  useEffect(() => {
    if (!drivesQuery.data?.items.length || localCurrentPath) {
      return;
    }
    setLocalPath(drivesQuery.data.items[0].path);
  }, [drivesQuery.data?.items, localCurrentPath, setLocalPath]);

  useEffect(() => {
    if (!sessionsQuery.data) {
      return;
    }
    syncSessions(sessionsQuery.data.items);
  }, [sessionsQuery.data, syncSessions]);

  return {
    sitesQuery,
    sessionsQuery,
    drivesQuery,
  };
}
