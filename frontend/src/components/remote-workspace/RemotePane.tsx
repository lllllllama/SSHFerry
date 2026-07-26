import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError, getErrorMessage } from '../../api/http';
import { createRemoteDirectory, deleteRemotePaths, listRemoteFiles, renameRemotePath } from '../../api/remoteFiles';
import type { RemoteEntry } from '../../api/types';
import { useI18n } from '../../i18n';
import { useUiStore } from '../../store/ui';
import { useWorkspaceStore, type RemotePaneState } from '../../store/workspace';
import { shortId } from '../../utils/format';
import { joinRemotePath } from '../../utils/paths';
import { StatusBadge } from '../common/StatusBadge';
import { FileTable } from '../file-browser/FileTable';

interface RemotePaneProps {
  pane: RemotePaneState;
  onCloseSession: (sessionId: string) => void;
  onQueueUploads: (localPaths: string[], sessionId: string, targetDir: string) => void | Promise<void>;
  onQueueDownloads: (sessionId: string, remotePaths: string[], targetDir: string) => void | Promise<void>;
  onQueueRemoteCopies: (
    srcSessionId: string,
    dstSessionId: string,
    remotePaths: string[],
    targetDir: string,
  ) => void | Promise<void>;
}

const EMPTY_REMOTE_SELECTION: string[] = [];

export function RemotePane({
  pane,
  onCloseSession,
  onQueueUploads,
  onQueueDownloads,
  onQueueRemoteCopies,
}: RemotePaneProps) {
  const queryClient = useQueryClient();
  const localSelection = useWorkspaceStore((state) => state.localSelection);
  const localCurrentPath = useWorkspaceStore((state) => state.localCurrentPath);
  const remoteSelection = useWorkspaceStore((state) => state.remoteSelections[pane.sessionId] ?? EMPTY_REMOTE_SELECTION);
  const activePaneId = useWorkspaceStore((state) => state.activePaneId);
  const setActivePane = useWorkspaceStore((state) => state.setActivePane);
  const setPanePath = useWorkspaceStore((state) => state.setPanePath);
  const setPaneStale = useWorkspaceStore((state) => state.setPaneStale);
  const setRemoteSelection = useWorkspaceStore((state) => state.setRemoteSelection);
  const toggleRemoteSelection = useWorkspaceStore((state) => state.toggleRemoteSelection);
  const openConfirm = useUiStore((state) => state.openConfirm);
  const pushToast = useUiStore((state) => state.pushToast);
  const [pathDraft, setPathDraft] = useState(pane.currentPath);
  const { t } = useI18n();

  const listingQuery = useQuery({
    queryKey: ['remote-list', pane.sessionId, pane.currentPath],
    queryFn: () => listRemoteFiles(pane.sessionId, pane.currentPath),
    enabled: !pane.stale,
    staleTime: 30_000,
    gcTime: 10 * 60_000,
    refetchOnMount: false,
    placeholderData: (previousData) => previousData,
  });

  const mkdirMutation = useMutation({ mutationFn: ({ path }: { path: string }) => createRemoteDirectory(pane.sessionId, path) });
  const renameMutation = useMutation({
    mutationFn: ({ oldPath, newPath }: { oldPath: string; newPath: string }) =>
      renameRemotePath(pane.sessionId, oldPath, newPath),
  });
  const deleteMutation = useMutation({ mutationFn: (paths: string[]) => deleteRemotePaths(pane.sessionId, paths, true) });

  const selectedEntries = listingQuery.data?.items.filter((entry) => remoteSelection.includes(entry.path)) ?? [];
  const firstSelectedEntry = selectedEntries[0] ?? null;

  useEffect(() => {
    setPathDraft(pane.currentPath);
  }, [pane.currentPath]);

  useEffect(() => {
    if (!listingQuery.data || listingQuery.isPlaceholderData || listingQuery.isFetching) {
      return;
    }
    if (listingQuery.data.current_path !== pane.currentPath) {
      setPanePath(pane.sessionId, listingQuery.data.current_path);
    }
  }, [
    listingQuery.data,
    listingQuery.isFetching,
    listingQuery.isPlaceholderData,
    pane.currentPath,
    pane.sessionId,
    setPanePath,
  ]);

  useEffect(() => {
    if (!(listingQuery.error instanceof ApiError)) {
      return;
    }
    if (listingQuery.error.status === 404) {
      setPaneStale(pane.sessionId, true);
    }
  }, [listingQuery.error, pane.sessionId, setPaneStale]);

  async function refreshListing() {
    await queryClient.invalidateQueries({ queryKey: ['remote-list', pane.sessionId] });
    await listingQuery.refetch();
  }

  async function handleDelete() {
    if (!selectedEntries.length) {
      return;
    }
    const labels = selectedEntries.map((entry) => entry.path).join('\n');
    openConfirm({
      title: t('remotePane.deleteTitle'),
      description: t('remotePane.deleteDescription', { labels }),
      confirmLabel: t('remotePane.deleteConfirm'),
      destructive: true,
      onConfirm: async () => {
        await deleteMutation.mutateAsync(selectedEntries.map((entry) => entry.path));
        setRemoteSelection(pane.sessionId, []);
        pushToast({ tone: 'success', title: t('remotePane.deleteToast') });
        await refreshListing();
      },
    });
  }

  if (pane.stale) {
    return (
      <section className={`remote-pane ${activePaneId === pane.sessionId ? 'is-active-pane' : ''}`}>
        <header className="panel-header remote-pane-header">
          <div>
            <h3>{pane.siteName}</h3>
            <p className="mono-cell">{t('common.session')} {shortId(pane.sessionId)} · {t('common.stale')}</p>
          </div>
          <button type="button" className="ghost-button" onClick={() => onCloseSession(pane.sessionId)}>
            {t('remotePane.closePane')}
          </button>
        </header>
        <div className="table-state table-state-error">
          <strong>{t('remotePane.staleTitle')}</strong>
          <p>{t('remotePane.staleBody')}</p>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`remote-pane ${activePaneId === pane.sessionId ? 'is-active-pane' : ''}`}
      onMouseDown={() => setActivePane(pane.sessionId)}
    >
      <header className="panel-header remote-pane-header">
        <div>
          <h3>{pane.siteName}</h3>
          <p className="mono-cell">{t('common.session')} {shortId(pane.sessionId)}</p>
        </div>
        <div className="panel-actions wrap-actions">
          <StatusBadge tone={listingQuery.isFetching ? 'warning' : 'success'}>
            {listingQuery.isFetching ? t('common.loading') : t('common.ready')}
          </StatusBadge>
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              if (listingQuery.data?.parent_path) {
                setPanePath(pane.sessionId, listingQuery.data.parent_path);
              }
            }}
            disabled={!listingQuery.data?.parent_path}
          >
            ..
          </button>
          <button type="button" className="ghost-button" onClick={() => void refreshListing()}>
            {t('common.refresh')}
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              const name = window.prompt(t('remotePane.createDirectoryPrompt'))?.trim();
              if (!name) {
                return;
              }
              void mkdirMutation
                .mutateAsync({ path: joinRemotePath(pane.currentPath, name) })
                .then(() => {
                  pushToast({ tone: 'success', title: t('remotePane.createDirectoryToast') });
                  void refreshListing();
                })
                .catch((error: unknown) => {
                  pushToast({
                    tone: 'danger',
                    title: t('remotePane.createDirectoryFailed'),
                    message: getErrorMessage(error),
                  });
                });
            }}
          >
            {t('common.add')}
          </button>
          <button type="button" className="ghost-button" onClick={() => onCloseSession(pane.sessionId)}>
            {t('common.close')}
          </button>
        </div>
      </header>

      <div className="path-bar">
        <input
          value={pathDraft}
          onChange={(event) => setPathDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && pathDraft.trim()) {
              setPanePath(pane.sessionId, pathDraft.trim());
            }
          }}
          placeholder={t('remotePane.pathPlaceholder')}
        />
      </div>

      <div className="inline-actions wrap-actions pane-subactions">
        <button
          type="button"
          className="ghost-button"
          onClick={() => void onQueueUploads(localSelection, pane.sessionId, pane.currentPath)}
          disabled={!localSelection.length}
        >
          {t('remotePane.uploadLocalSelection')}
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={() => void onQueueDownloads(pane.sessionId, remoteSelection, localCurrentPath)}
          disabled={!remoteSelection.length || !localCurrentPath}
        >
          {t('remotePane.downloadSelection')}
        </button>
        <button
          type="button"
          className="ghost-button"
          disabled={!firstSelectedEntry}
          onClick={() => {
            if (!firstSelectedEntry) {
              return;
            }
            const nextName = window.prompt(t('remotePane.renamePrompt'), firstSelectedEntry.name)?.trim();
            if (!nextName || nextName === firstSelectedEntry.name) {
              return;
            }
            const currentDir = listingQuery.data?.current_path || pane.currentPath;
            void renameMutation
              .mutateAsync({
                oldPath: firstSelectedEntry.path,
                newPath: joinRemotePath(currentDir, nextName),
              })
              .then(() => {
                pushToast({ tone: 'success', title: t('remotePane.renameToast') });
                void refreshListing();
              })
              .catch((error: unknown) => {
                pushToast({
                  tone: 'danger',
                  title: t('remotePane.renameFailed'),
                  message: getErrorMessage(error),
                });
              });
          }}
        >
          {t('common.rename')}
        </button>
        <button type="button" className="ghost-button danger-text" disabled={!selectedEntries.length} onClick={handleDelete}>
          {t('common.delete')}
        </button>
      </div>

      <FileTable
        entries={listingQuery.data?.items ?? []}
        selectedPaths={remoteSelection}
        currentPath={listingQuery.data?.current_path || pane.currentPath}
        emptyMessage={t('remotePane.empty')}
        isLoading={listingQuery.isPending}
        errorMessage={listingQuery.error ? getErrorMessage(listingQuery.error, t('remotePane.loadError')) : null}
        stale={pane.stale}
        onSelect={(path, multi) => toggleRemoteSelection(pane.sessionId, path, multi)}
        onSelectRange={(paths) => setRemoteSelection(pane.sessionId, paths)}
        onDeleteSelection={handleDelete}
        onActivate={(entry: RemoteEntry) => {
          if (entry.is_dir) {
            setPanePath(pane.sessionId, entry.path);
          }
        }}
        dragPayloadFactory={(entry) => ({
          kind: 'remote',
          sessionId: pane.sessionId,
          paths: remoteSelection.includes(entry.path) ? remoteSelection : [entry.path],
        })}
        onDropTransfer={(payload, targetPath) => {
          if (payload.kind === 'local') {
            void onQueueUploads(payload.paths, pane.sessionId, targetPath);
            return;
          }
          if (!payload.sessionId || payload.sessionId === pane.sessionId) {
            return;
          }
          void onQueueRemoteCopies(payload.sessionId, pane.sessionId, payload.paths, targetPath);
        }}
      />
    </section>
  );
}
