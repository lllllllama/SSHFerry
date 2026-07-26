import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiError, getErrorMessage } from '../../api/http';
import { closeSession } from '../../api/sessions';
import type { TransferDragPayload } from '../../api/types';
import {
  createDownloadTask,
  createRemoteCopyTask,
  createUploadTask,
  createWorkspaceDownloadTask,
  createWorkspaceUploadTask,
} from '../../api/tasks';
import { ActivityFeed } from '../../components/activity/ActivityFeed';
import { AppTopBar } from '../../components/layout/AppTopBar';
import { RemoteWorkspace } from '../../components/remote-workspace/RemoteWorkspace';
import { SiteEditorModal } from '../../components/sites/SiteEditorModal';
import { SiteSidebar } from '../../components/sites/SiteSidebar';
import { TaskCenter } from '../../components/tasks/TaskCenter';
import { MiddleWorkspace } from '../../components/workspace/MiddleWorkspace';
import { useI18n } from '../../i18n';
import { useAuthStore } from '../../store/auth';
import { useUiStore } from '../../store/ui';
import { useWorkspaceStore } from '../../store/workspace';
import { basename, joinLocalPath, joinRemotePath } from '../../utils/paths';

function summarizeResults(results: PromiseSettledResult<unknown>[]) {
  const successCount = results.filter((result) => result.status === 'fulfilled').length;
  return { successCount, total: results.length };
}

export function WorkspacePage() {
  const queryClient = useQueryClient();
  const authenticated = useAuthStore((state) => state.status === 'authenticated');
  const health = useAuthStore((state) => state.health);
  const panes = useWorkspaceStore((state) => state.panes);
  const centerPanelMode = useWorkspaceStore((state) => state.centerPanelMode);
  const centerSessionId = useWorkspaceStore((state) => state.centerSessionId);
  const setCenterPanelMode = useWorkspaceStore((state) => state.setCenterPanelMode);
  const setCenterSessionId = useWorkspaceStore((state) => state.setCenterSessionId);
  const protocolOverride = useUiStore((state) => state.protocolOverride);
  const pushToast = useUiStore((state) => state.pushToast);
  const { t } = useI18n();
  const useDirectLocalMode = health?.runtime_mode === 'local-dev';

  const uploadMutation = useMutation({ mutationFn: createWorkspaceUploadTask });
  const localUploadMutation = useMutation({ mutationFn: createUploadTask });
  const downloadMutation = useMutation({ mutationFn: createWorkspaceDownloadTask });
  const localDownloadMutation = useMutation({ mutationFn: createDownloadTask });
  const remoteCopyMutation = useMutation({ mutationFn: createRemoteCopyTask });
  const closeSessionMutation = useMutation({ mutationFn: closeSession });

  if (!authenticated) {
    return (
      <main className="bootstrap-page">
        <section className="bootstrap-panel">
          <div className="eyebrow">{t('nav.workspace')}</div>
          <h1>{t('workspace.waitTitle')}</h1>
          <p>{t('workspace.waitDescription')}</p>
        </section>
      </main>
    );
  }

  async function queueUploads(localPaths: string[], sessionId: string, targetDir: string) {
    if (!localPaths.length) {
      pushToast({ tone: 'warning', title: t('workspace.toast.noUploadSelection') });
      return;
    }
    const results = await Promise.allSettled(
      localPaths.map((localPath) =>
        useDirectLocalMode
          ? localUploadMutation.mutateAsync({
              session_id: sessionId,
              local_path: localPath,
              remote_path: joinRemotePath(targetDir, basename(localPath)),
              engine: protocolOverride,
            })
          : uploadMutation.mutateAsync({
              session_id: sessionId,
              workspace_path: localPath,
              remote_path: joinRemotePath(targetDir, basename(localPath)),
              engine: protocolOverride,
            }),
      ),
    );
    const summary = summarizeResults(results);
    pushToast({
      tone: summary.successCount === summary.total ? 'success' : 'warning',
      title: t('workspace.toast.uploadSubmitted'),
      message: t('workspace.toast.queueSummary', {
        successCount: summary.successCount,
        total: summary.total,
      }),
    });
  }

  async function queueDownloads(sessionId: string, remotePaths: string[], targetDir: string) {
    if (!remotePaths.length || !targetDir) {
      pushToast({ tone: 'warning', title: t('workspace.toast.noDownloadTarget') });
      return;
    }
    const results = await Promise.allSettled(
      remotePaths.map((remotePath) =>
        useDirectLocalMode
          ? localDownloadMutation.mutateAsync({
              session_id: sessionId,
              remote_path: remotePath,
              local_path: joinLocalPath(targetDir, basename(remotePath)),
              engine: protocolOverride,
            })
          : downloadMutation.mutateAsync({
              session_id: sessionId,
              remote_path: remotePath,
              workspace_path: joinLocalPath(targetDir, basename(remotePath)),
              engine: protocolOverride,
            }),
      ),
    );
    const summary = summarizeResults(results);
    pushToast({
      tone: summary.successCount === summary.total ? 'success' : 'warning',
      title: t('workspace.toast.downloadSubmitted'),
      message: t('workspace.toast.queueSummary', {
        successCount: summary.successCount,
        total: summary.total,
      }),
    });
  }

  async function queueRemoteCopies(
    srcSessionId: string,
    dstSessionId: string,
    remotePaths: string[],
    targetDir: string,
  ) {
    if (!remotePaths.length) {
      pushToast({ tone: 'warning', title: t('workspace.toast.noRemoteCopySelection') });
      return;
    }
    const results = await Promise.allSettled(
      remotePaths.map((remotePath) =>
        remoteCopyMutation.mutateAsync({
          src_session_id: srcSessionId,
          dst_session_id: dstSessionId,
          src_path: remotePath,
          dst_path: joinRemotePath(targetDir, basename(remotePath)),
          engine: protocolOverride,
        }),
      ),
    );
    const summary = summarizeResults(results);
    pushToast({
      tone: summary.successCount === summary.total ? 'success' : 'warning',
      title: t('workspace.toast.remoteCopySubmitted'),
      message: t('workspace.toast.queueSummary', {
        successCount: summary.successCount,
        total: summary.total,
      }),
    });
  }

  async function handleLocalDrop(payload: TransferDragPayload, targetDir: string) {
    if (payload.kind !== 'remote' || !payload.sessionId) {
      return;
    }
    await queueDownloads(payload.sessionId, payload.paths, targetDir);
  }

  async function handleCloseSession(sessionId: string) {
    try {
      await closeSessionMutation.mutateAsync({ session_id: sessionId });
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) {
        pushToast({
          tone: 'danger',
          title: t('workspace.toast.sessionCloseFailed'),
          message: getErrorMessage(error),
        });
        return;
      }
      // 404 means the backend no longer knows this session; treat it as already closed.
    }
    useWorkspaceStore.getState().closePane(sessionId);
    await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    pushToast({ tone: 'success', title: t('workspace.toast.sessionClosed') });
  }

  const pinnedRemoteMode = centerPanelMode === 'remote' && Boolean(centerSessionId);
  const rightPanes = pinnedRemoteMode ? panes.filter((pane) => pane.sessionId !== centerSessionId) : panes;

  return (
    <main className="app-shell workspace-shell">
      <AppTopBar />
      <section className="workspace-grid">
        <SiteSidebar />
        <MiddleWorkspace
          panes={panes}
          mode={centerPanelMode}
          centerSessionId={centerSessionId}
          onChangeMode={setCenterPanelMode}
          onQueueLocalDownloads={handleLocalDrop}
          onCloseSession={(sessionId) => {
            void handleCloseSession(sessionId);
          }}
          onQueueUploads={queueUploads}
          onQueueDownloads={queueDownloads}
          onQueueRemoteCopies={queueRemoteCopies}
        />
        <RemoteWorkspace
          panes={rightPanes}
          emptyTitle={pinnedRemoteMode ? t('workspace.secondaryRemoteEmptyTitle') : undefined}
          emptyBody={pinnedRemoteMode ? t('workspace.secondaryRemoteEmptyBody') : undefined}
          onCloseSession={(sessionId) => {
            void handleCloseSession(sessionId);
          }}
          onQueueUploads={queueUploads}
          onQueueDownloads={queueDownloads}
          onQueueRemoteCopies={queueRemoteCopies}
        />
      </section>
      <section className="workspace-bottom-grid">
        <TaskCenter />
        <ActivityFeed />
      </section>
      <SiteEditorModal />
    </main>
  );
}
