import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';

import { closeSession } from '../../api/sessions';
import type { TransferDragPayload } from '../../api/types';
import { createDownloadTask, createRemoteCopyTask, createUploadTask } from '../../api/tasks';
import { LocalPanel } from '../../components/file-browser/LocalPanel';
import { AppTopBar } from '../../components/layout/AppTopBar';
import { LogPlaceholder } from '../../components/logs/LogPlaceholder';
import { RemoteWorkspace } from '../../components/remote-workspace/RemoteWorkspace';
import { SiteEditorModal } from '../../components/sites/SiteEditorModal';
import { SiteSidebar } from '../../components/sites/SiteSidebar';
import { TaskCenter } from '../../components/tasks/TaskCenter';
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
  const status = useAuthStore((state) => state.status);
  const panes = useWorkspaceStore((state) => state.panes);
  const protocolOverride = useUiStore((state) => state.protocolOverride);
  const pushToast = useUiStore((state) => state.pushToast);
  const { t } = useI18n();

  const uploadMutation = useMutation({ mutationFn: createUploadTask });
  const downloadMutation = useMutation({ mutationFn: createDownloadTask });
  const remoteCopyMutation = useMutation({ mutationFn: createRemoteCopyTask });
  const closeSessionMutation = useMutation({ mutationFn: closeSession });

  if (status === 'error') {
    return <Navigate to="/" replace />;
  }

  if (status !== 'ready') {
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
        uploadMutation.mutateAsync({
          session_id: sessionId,
          local_path: localPath,
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
        downloadMutation.mutateAsync({
          session_id: sessionId,
          remote_path: remotePath,
          local_path: joinLocalPath(targetDir, basename(remotePath)),
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
    await closeSessionMutation.mutateAsync({ session_id: sessionId });
    useWorkspaceStore.getState().closePane(sessionId);
    await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    pushToast({ tone: 'success', title: t('workspace.toast.sessionClosed') });
  }

  return (
    <main className="app-shell">
      <AppTopBar />
      <section className="workspace-grid">
        <SiteSidebar />
        <LocalPanel onQueueDownloads={handleLocalDrop} />
        <RemoteWorkspace
          panes={panes}
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
        <LogPlaceholder />
      </section>
      <SiteEditorModal />
    </main>
  );
}
