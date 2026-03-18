import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError, getErrorMessage } from '../../api/http';
import { createRemoteDirectory, deleteRemotePath, listRemoteFiles, renameRemotePath } from '../../api/remoteFiles';
import type { RemoteEntry } from '../../api/types';
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
  const remoteSelection = useWorkspaceStore((state) => state.remoteSelections[pane.sessionId] ?? []);
  const activePaneId = useWorkspaceStore((state) => state.activePaneId);
  const setActivePane = useWorkspaceStore((state) => state.setActivePane);
  const setPanePath = useWorkspaceStore((state) => state.setPanePath);
  const setPanePathDraft = useWorkspaceStore((state) => state.setPanePathDraft);
  const setPaneStale = useWorkspaceStore((state) => state.setPaneStale);
  const toggleRemoteSelection = useWorkspaceStore((state) => state.toggleRemoteSelection);
  const openConfirm = useUiStore((state) => state.openConfirm);
  const pushToast = useUiStore((state) => state.pushToast);

  const listingQuery = useQuery({
    queryKey: ['remote-list', pane.sessionId, pane.currentPath],
    queryFn: () => listRemoteFiles(pane.sessionId, pane.currentPath),
    enabled: !pane.stale,
  });

  const mkdirMutation = useMutation({ mutationFn: ({ path }: { path: string }) => createRemoteDirectory(pane.sessionId, path) });
  const renameMutation = useMutation({
    mutationFn: ({ oldPath, newPath }: { oldPath: string; newPath: string }) =>
      renameRemotePath(pane.sessionId, oldPath, newPath),
  });
  const deleteMutation = useMutation({ mutationFn: (path: string) => deleteRemotePath(pane.sessionId, path, true) });

  const selectedEntries = listingQuery.data?.items.filter((entry) => remoteSelection.includes(entry.path)) ?? [];
  const firstSelectedEntry = selectedEntries[0] ?? null;

  useEffect(() => {
    if (!listingQuery.data) {
      return;
    }
    if (listingQuery.data.current_path !== pane.currentPath) {
      setPanePath(pane.sessionId, listingQuery.data.current_path);
    }
  }, [listingQuery.data, pane.currentPath, pane.sessionId, setPanePath]);

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
      title: '删除远端路径',
      description: `将删除以下远端对象：\n${labels}`,
      confirmLabel: '确认删除',
      destructive: true,
      onConfirm: async () => {
        await Promise.all(selectedEntries.map((entry) => deleteMutation.mutateAsync(entry.path)));
        pushToast({ tone: 'success', title: '远端删除请求已提交' });
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
            <p className="mono-cell">{shortId(pane.sessionId)} · stale</p>
          </div>
          <button type="button" className="ghost-button" onClick={() => onCloseSession(pane.sessionId)}>
            Close Pane
          </button>
        </header>
        <div className="table-state table-state-error">
          <strong>Session 已失效</strong>
          <p>后端已重启或该会话不存在。请从左侧重新打开站点，或直接关闭当前 pane。</p>
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
          <p className="mono-cell">Session {shortId(pane.sessionId)}</p>
        </div>
        <div className="panel-actions wrap-actions">
          <StatusBadge tone={listingQuery.isFetching ? 'warning' : 'success'}>
            {listingQuery.isFetching ? 'loading' : 'ready'}
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
            Refresh
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              const name = window.prompt('输入新目录名');
              if (!name) {
                return;
              }
              void mkdirMutation.mutateAsync({ path: joinRemotePath(pane.currentPath, name) }).then(() => {
                pushToast({ tone: 'success', title: '远端目录已创建' });
                void refreshListing();
              });
            }}
          >
            New Dir
          </button>
          <button type="button" className="ghost-button" onClick={() => onCloseSession(pane.sessionId)}>
            Close
          </button>
        </div>
      </header>

      <div className="path-bar">
        <input
          value={pane.pathDraft}
          onChange={(event) => setPanePathDraft(pane.sessionId, event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && pane.pathDraft.trim()) {
              setPanePath(pane.sessionId, pane.pathDraft.trim());
            }
          }}
          placeholder="输入远端路径"
        />
      </div>

      <div className="inline-actions wrap-actions pane-subactions">
        <button
          type="button"
          className="ghost-button"
          onClick={() => void onQueueUploads(localSelection, pane.sessionId, pane.currentPath)}
          disabled={!localSelection.length}
        >
          Upload Local Selection
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={() => void onQueueDownloads(pane.sessionId, remoteSelection, localCurrentPath)}
          disabled={!remoteSelection.length || !localCurrentPath}
        >
          Download Selection
        </button>
        <button
          type="button"
          className="ghost-button"
          disabled={!firstSelectedEntry}
          onClick={() => {
            if (!firstSelectedEntry) {
              return;
            }
            const nextName = window.prompt('输入新的文件名或目录名', firstSelectedEntry.name);
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
                pushToast({ tone: 'success', title: '远端路径已重命名' });
                void refreshListing();
              });
          }}
        >
          Rename
        </button>
        <button type="button" className="ghost-button danger-text" disabled={!selectedEntries.length} onClick={handleDelete}>
          Delete
        </button>
      </div>

      <FileTable
        entries={listingQuery.data?.items ?? []}
        selectedPaths={remoteSelection}
        currentPath={listingQuery.data?.current_path || pane.currentPath}
        emptyMessage="当前远端目录为空。"
        isLoading={listingQuery.isPending}
        errorMessage={listingQuery.error ? getErrorMessage(listingQuery.error, '无法读取远端目录') : null}
        stale={pane.stale}
        onSelect={(path, multi) => toggleRemoteSelection(pane.sessionId, path, multi)}
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
