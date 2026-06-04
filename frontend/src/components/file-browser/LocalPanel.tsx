import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getHealth } from '../../api/auth';
import { ApiError, getErrorMessage } from '../../api/http';
import { listLocalDrives, listLocalFiles, searchLocalFiles } from '../../api/localFiles';
import {
  deleteWorkspaceItems,
  listWorkspaceItems,
  resetWorkspaceData,
  statWorkspacePath,
  uploadWorkspaceFiles,
} from '../../api/workspace';
import type { TaskItem, TransferDragPayload } from '../../api/types';
import { useI18n } from '../../i18n';
import { useAuthStore } from '../../store/auth';
import { useTasksStore } from '../../store/tasks';
import { useUiStore } from '../../store/ui';
import { useWorkspaceStore } from '../../store/workspace';
import { formatBytes } from '../../utils/format';
import { FileTable } from './FileTable';

interface LocalPanelProps {
  onQueueDownloads: (payload: TransferDragPayload, targetDir: string) => void | Promise<void>;
}

type BrowserFile = File & { webkitRelativePath?: string };

const LOCAL_SEARCH_DEBOUNCE_MS = 180;

function isAggregateUpload(relativePaths: string[]): boolean {
  return relativePaths.length > 1 || relativePaths.some((path) => path.includes('/'));
}

function buildWorkspaceLabel(path: string): string {
  const normalized = path.trim() || '/';
  return `workspace:${normalized}`;
}

function normalizeDisplayPath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+$/, '');
}

function buildLocalSearchLocation(entryPath: string, entryName: string, rootPath: string): string {
  const root = normalizeDisplayPath(rootPath);
  const fullPath = normalizeDisplayPath(entryPath);
  const parentPath = normalizeDisplayPath(fullPath.slice(0, Math.max(0, fullPath.length - entryName.length)));
  const rootKey = root.toLowerCase();
  const parentKey = parentPath.toLowerCase();
  if (root && parentKey === rootKey) {
    return '.';
  }
  if (root && parentKey.startsWith(`${rootKey}/`)) {
    return parentPath.slice(root.length + 1);
  }
  return parentPath || '.';
}

function buildUploadSourcePath(relativePaths: string[]): string {
  if (!relativePaths.length) {
    return '/upload';
  }
  if (relativePaths.length === 1) {
    return `/${relativePaths[0].replace(/^\/+/, '')}`;
  }
  return '/browser-upload';
}

function buildUploadSourceLabel(relativePaths: string[]): string {
  if (!relativePaths.length) {
    return 'local:/upload';
  }
  if (relativePaths.length === 1) {
    return `local:/${relativePaths[0].replace(/^\/+/, '')}`;
  }
  return `local:${relativePaths.length} items`;
}

function resolveUploadProgressSnapshot(files: File[], relativePaths: string[], bytesDone: number) {
  let consumedBytes = 0;
  let completedFiles = 0;

  for (let index = 0; index < files.length; index += 1) {
    const fileSize = files[index]?.size ?? 0;
    const nextBytes = consumedBytes + fileSize;
    if (bytesDone >= nextBytes) {
      completedFiles += 1;
      consumedBytes = nextBytes;
      continue;
    }
    return {
      completedFiles,
      currentFile: relativePaths[index] ?? files[index]?.name ?? '',
    };
  }

  return {
    completedFiles: files.length,
    currentFile: '',
  };
}

function createClientUploadTask(taskId: string, files: File[], relativePaths: string[], targetPath: string): TaskItem {
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const aggregateUpload = isAggregateUpload(relativePaths);
  return {
    task_id: taskId,
    kind: aggregateUpload ? 'folder_transfer' : 'file_transfer',
    engine: 'http',
    status: 'running',
    src: buildUploadSourcePath(relativePaths),
    dst: targetPath,
    src_endpoint_type: 'local',
    dst_endpoint_type: 'workspace',
    src_session_id: null,
    dst_session_id: null,
    src_display_name: null,
    dst_display_name: null,
    src_label: buildUploadSourceLabel(relativePaths),
    dst_label: buildWorkspaceLabel(targetPath),
    bytes_total: totalBytes,
    bytes_done: 0,
    progress_percent: 0,
    speed: 0,
    retries: 0,
    error_code: null,
    error_message: null,
    start_time: Date.now() / 1000,
    end_time: null,
    interrupted: false,
    paused: false,
    skipped: false,
    subtask_count: aggregateUpload ? files.length : 0,
    subtask_done: 0,
    current_file: relativePaths[0] ?? files[0]?.name ?? '',
    is_finished: false,
  };
}

export function LocalPanel({ onQueueDownloads }: LocalPanelProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const uploadMenuRef = useRef<HTMLDetailsElement | null>(null);
  const [localSearchText, setLocalSearchText] = useState('');
  const [debouncedLocalSearchText, setDebouncedLocalSearchText] = useState('');
  const localCurrentPath = useWorkspaceStore((state) => state.localCurrentPath);
  const localPathDraft = useWorkspaceStore((state) => state.localPathDraft);
  const localSelection = useWorkspaceStore((state) => state.localSelection);
  const setLocalPath = useWorkspaceStore((state) => state.setLocalPath);
  const setLocalPathDraft = useWorkspaceStore((state) => state.setLocalPathDraft);
  const setLocalSelection = useWorkspaceStore((state) => state.setLocalSelection);
  const toggleLocalSelection = useWorkspaceStore((state) => state.toggleLocalSelection);
  const upsertClientTask = useTasksStore((state) => state.upsertClientTask);
  const patchClientTask = useTasksStore((state) => state.patchClientTask);
  const cancelClientTask = useTasksStore((state) => state.cancelClientTask);
  const clearClientTasks = useTasksStore((state) => state.clearClientTasks);
  const health = useAuthStore((state) => state.health);
  const openConfirm = useUiStore((state) => state.openConfirm);
  const pushToast = useUiStore((state) => state.pushToast);
  const { t } = useI18n();

  const isDirectLocalMode = health?.runtime_mode === 'local-dev';
  const currentPath = localCurrentPath || (isDirectLocalMode ? '' : '/');
  const resetSupported = health?.features?.includes('workspace-reset') ?? false;
  const localDrivesQuery = useQuery({
    queryKey: ['local-drives'],
    queryFn: listLocalDrives,
    enabled: isDirectLocalMode,
    staleTime: 60000,
  });

  const listingQuery = useQuery({
    queryKey: [isDirectLocalMode ? 'local-files-list' : 'workspace-list', currentPath],
    queryFn: () => (isDirectLocalMode ? listLocalFiles(currentPath) : listWorkspaceItems(currentPath)),
    enabled: isDirectLocalMode ? Boolean(currentPath.trim()) : true,
  });

  const localSearchQuery = debouncedLocalSearchText.trim();
  const isLocalSearchActive = isDirectLocalMode && Boolean(currentPath.trim()) && localSearchQuery.length > 0;
  const localSearchResultQuery = useQuery({
    queryKey: ['local-files-search', currentPath, localSearchQuery],
    queryFn: () => searchLocalFiles(currentPath, localSearchQuery),
    enabled: isLocalSearchActive,
    staleTime: 5000,
  });

  const statsQuery = useQuery({
    queryKey: ['workspace-stat', currentPath],
    queryFn: () => statWorkspacePath(currentPath),
    enabled: !isDirectLocalMode,
  });

  const uploadMutation = useMutation({ mutationFn: uploadWorkspaceFiles });
  const deleteMutation = useMutation({ mutationFn: deleteWorkspaceItems });
  const resetMutation = useMutation({ mutationFn: resetWorkspaceData });

  const activeEntries = (isLocalSearchActive ? localSearchResultQuery.data?.items : listingQuery.data?.items) ?? [];
  const selectedEntries = activeEntries.filter((entry) => localSelection.includes(entry.path));
  const summary = !isDirectLocalMode && statsQuery.data
    ? t('localPanel.summary', {
        files: statsQuery.data.file_count,
        dirs: statsQuery.data.dir_count,
        size: formatBytes(statsQuery.data.total_size),
      })
    : null;

  useEffect(() => {
    if (!isDirectLocalMode || localCurrentPath || !localDrivesQuery.data?.items.length) {
      return;
    }
    setLocalPath(localDrivesQuery.data.items[0].path);
  }, [isDirectLocalMode, localCurrentPath, localDrivesQuery.data?.items, setLocalPath]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedLocalSearchText(localSearchText.trim());
    }, LOCAL_SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [localSearchText]);

  useEffect(() => {
    if (!listingQuery.data) {
      return;
    }
    if (listingQuery.data.current_path !== currentPath) {
      setLocalPath(listingQuery.data.current_path);
    }
  }, [currentPath, listingQuery.data, setLocalPath]);

  async function refreshWorkspace() {
    await Promise.all([
      listingQuery.refetch(),
      ...(isLocalSearchActive ? [localSearchResultQuery.refetch()] : []),
      ...(!isDirectLocalMode ? [statsQuery.refetch()] : []),
    ]);
  }

  function closeUploadMenu() {
    if (uploadMenuRef.current) {
      uploadMenuRef.current.open = false;
    }
  }

  async function handleUploadSelection(files: FileList | null) {
    const selectedFiles = Array.from(files ?? []);
    if (!selectedFiles.length) {
      return;
    }

    const relativePaths = selectedFiles.map((file) => {
      const browserFile = file as BrowserFile;
      return browserFile.webkitRelativePath && browserFile.webkitRelativePath.trim()
        ? browserFile.webkitRelativePath
        : file.name;
    });
    const targetPath = listingQuery.data?.current_path || currentPath;
    const totalBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);
    const aggregateUpload = isAggregateUpload(relativePaths);
    const taskId = `workspace-upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const controller = new AbortController();
    const uploadTask = createClientUploadTask(taskId, selectedFiles, relativePaths, targetPath);
    upsertClientTask(uploadTask, { abort: () => controller.abort() });

    let previousBytesDone = 0;
    let previousProgressAt = performance.now();

    try {
      await uploadMutation.mutateAsync({
        targetPath,
        files: selectedFiles,
        relativePaths,
        signal: controller.signal,
        onUploadProgress: (event) => {
          const ratio = typeof event.progress === 'number'
            ? event.progress
            : typeof event.total === 'number' && event.total > 0
              ? event.loaded / event.total
              : 0;
          const normalizedRatio = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
          const bytesDone = totalBytes > 0 ? Math.min(totalBytes, Math.round(totalBytes * normalizedRatio)) : 0;
          const now = performance.now();
          const deltaBytes = Math.max(0, bytesDone - previousBytesDone);
          const deltaMs = Math.max(1, now - previousProgressAt);
          const speed = typeof event.rate === 'number' && event.rate > 0
            ? event.rate
            : (deltaBytes / deltaMs) * 1000;
          previousBytesDone = bytesDone;
          previousProgressAt = now;

          const progressSnapshot = resolveUploadProgressSnapshot(selectedFiles, relativePaths, bytesDone);
          patchClientTask(taskId, {
            status: 'running',
            bytes_done: bytesDone,
            progress_percent: totalBytes > 0 ? normalizedRatio * 100 : 0,
            speed,
            subtask_done: aggregateUpload ? progressSnapshot.completedFiles : 0,
            current_file: progressSnapshot.currentFile,
          });
        },
      });

      patchClientTask(taskId, {
        status: 'done',
        bytes_done: totalBytes,
        progress_percent: 100,
        speed: 0,
        error_message: null,
        end_time: Date.now() / 1000,
        interrupted: false,
        subtask_done: aggregateUpload ? selectedFiles.length : 0,
        current_file: '',
        is_finished: true,
      });
      pushToast({
        tone: 'success',
        title: t('localPanel.uploaded'),
        message: t('localPanel.uploadedSummary', { total: selectedFiles.length }),
      });
      await refreshWorkspace();
    } catch (error) {
      const canceled = error instanceof Error && error.name === 'CanceledError';
      patchClientTask(taskId, {
        status: canceled ? 'canceled' : 'failed',
        speed: 0,
        end_time: Date.now() / 1000,
        interrupted: canceled,
        error_message: canceled ? null : getErrorMessage(error, t('localPanel.uploadFailed')),
        is_finished: true,
      });
      pushToast({
        tone: canceled ? 'warning' : 'danger',
        title: canceled ? t('localPanel.uploadCanceled') : t('localPanel.uploadFailed'),
        message: canceled ? undefined : getErrorMessage(error, t('localPanel.uploadFailed')),
      });
    }
  }

  function handleDelete() {
    if (!selectedEntries.length) {
      return;
    }
    const labels = selectedEntries.map((entry) => entry.path).join('\n');
    openConfirm({
      title: t('localPanel.deleteTitle'),
      description: t('localPanel.deleteDescription', { labels }),
      confirmLabel: t('localPanel.deleteConfirm'),
      destructive: true,
      onConfirm: async () => {
        await deleteMutation.mutateAsync(selectedEntries.map((entry) => entry.path));
        setLocalSelection([]);
        pushToast({ tone: 'success', title: t('localPanel.deleted') });
        await refreshWorkspace();
      },
    });
  }

  async function handleResetAll() {
    let latestResetSupported = resetSupported;

    if (!latestResetSupported) {
      try {
        const latestHealth = await getHealth();
        latestResetSupported = latestHealth.features?.includes('workspace-reset') ?? false;
      } catch {
        latestResetSupported = false;
      }
    }

    if (!latestResetSupported) {
      pushToast({
        tone: 'warning',
        title: t('localPanel.resetFailed'),
        message: t('localPanel.resetBackendRestartRequired'),
      });
      return;
    }

    openConfirm({
      title: t('localPanel.resetTitle'),
      description: t('localPanel.resetDescription'),
      confirmLabel: t('localPanel.resetConfirm'),
      destructive: true,
      onConfirm: async () => {
        try {
          const { clientItems } = useTasksStore.getState();
          clientItems
            .filter((task) => !task.is_finished)
            .forEach((task) => {
              cancelClientTask(task.task_id);
            });

          const response = await resetMutation.mutateAsync();
          clearClientTasks();

          const workspaceState = useWorkspaceStore.getState();
          for (const pane of [...workspaceState.panes]) {
            workspaceState.closePane(pane.sessionId);
          }
          workspaceState.setSelectedSiteName(null);
          workspaceState.setCenterPanelMode('local');
          workspaceState.setLocalSelection([]);
          workspaceState.setLocalPath('/');

          await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['workspace-list'] }),
            queryClient.invalidateQueries({ queryKey: ['workspace-stat'] }),
            queryClient.invalidateQueries({ queryKey: ['sites'] }),
            queryClient.invalidateQueries({ queryKey: ['sessions'] }),
          ]);

          pushToast({
            tone: 'success',
            title: t('localPanel.resetDone'),
            message: t('localPanel.resetSummary', {
              sites: response.deleted_site_count,
              sessions: response.closed_session_count,
              tasks: response.cleared_task_count,
              files: response.workspace_file_count,
              dirs: response.workspace_dir_count,
            }),
          });
        } catch (error) {
          const message = error instanceof ApiError && error.status === 404
            ? t('localPanel.resetBackendRestartRequired')
            : getErrorMessage(error, t('localPanel.resetFailed'));
          pushToast({
            tone: 'danger',
            title: t('localPanel.resetFailed'),
            message,
          });
        }
      },
    });
  }

  return (
    <section className="panel-shell local-panel">
      <header className="panel-header local-panel-header">
        <div className="local-panel-header-copy">
          <h3>{isDirectLocalMode ? t('localPanel.localModeTitle') : t('localPanel.title')}</h3>
          <p>{isDirectLocalMode ? t('localPanel.localModeDescription') : t('localPanel.description')}</p>
          {summary ? <p className="mono-cell">{summary}</p> : null}
        </div>
        <div className="local-panel-actions">
          <button
            type="button"
            className="ghost-button local-panel-nav-button"
            onClick={() => {
              if (listingQuery.data?.parent_path) {
                setLocalPath(listingQuery.data.parent_path);
              }
            }}
            disabled={!listingQuery.data?.parent_path}
          >
            ..
          </button>
          <button type="button" className="ghost-button" onClick={() => void refreshWorkspace()}>
            {t('common.refresh')}
          </button>
          {isDirectLocalMode && localDrivesQuery.data?.items.length ? (
            <select
              className="local-drive-select"
              value={
                localDrivesQuery.data.items.find((drive) => currentPath.startsWith(drive.path))
                  ?.path ?? ''
              }
              onChange={(event) => {
                if (event.target.value) {
                  setLocalPath(event.target.value);
                }
              }}
            >
              <option value="">{t('localPanel.localModeDrivePlaceholder')}</option>
              {localDrivesQuery.data.items.map((drive) => (
                <option key={drive.path} value={drive.path}>
                  {drive.label}
                </option>
              ))}
            </select>
          ) : null}
          {!isDirectLocalMode ? (
            <>
              <details ref={uploadMenuRef} className="local-panel-upload-menu">
                <summary className="ghost-button local-panel-upload-trigger">{t('localPanel.uploadAction')}</summary>
                <div className="local-panel-upload-sheet">
                  <button
                    type="button"
                    className="local-panel-upload-option"
                    onClick={() => {
                      closeUploadMenu();
                      fileInputRef.current?.click();
                    }}
                  >
                    {t('localPanel.uploadFiles')}
                  </button>
                  <button
                    type="button"
                    className="local-panel-upload-option"
                    onClick={() => {
                      closeUploadMenu();
                      folderInputRef.current?.click();
                    }}
                  >
                    {t('localPanel.uploadFolder')}
                  </button>
                </div>
              </details>
              <button
                type="button"
                className="ghost-button danger-text"
                disabled={!selectedEntries.length}
                onClick={handleDelete}
              >
                {t('localPanel.deleteSelected')}
              </button>
              <button
                type="button"
                className="ghost-button danger-text"
                disabled={resetMutation.isPending}
                title={!resetSupported ? t('localPanel.resetBackendRestartRequired') : undefined}
                onClick={handleResetAll}
              >
                {t('localPanel.resetAction')}
              </button>
            </>
          ) : null}
        </div>
        {!isDirectLocalMode ? (
          <>
            <input
              ref={fileInputRef}
              hidden
              type="file"
              multiple
              onChange={(event) => {
                void handleUploadSelection(event.target.files);
                event.currentTarget.value = '';
              }}
            />
            <input
              ref={folderInputRef}
              hidden
              type="file"
              multiple
              {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
              onChange={(event) => {
                void handleUploadSelection(event.target.files);
                event.currentTarget.value = '';
              }}
            />
          </>
        ) : null}
      </header>
      <div className="path-bar">
        <input
          value={localPathDraft}
          onChange={(event) => setLocalPathDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && localPathDraft.trim()) {
              setLocalPath(localPathDraft.trim());
            }
          }}
          placeholder={isDirectLocalMode ? t('localPanel.localModePathPlaceholder') : t('localPanel.pathPlaceholder')}
        />
      </div>
      {isDirectLocalMode ? (
        <div className="path-bar local-search-bar" role="search">
          <div className="inline-form-row">
            <input
              value={localSearchText}
              onChange={(event) => setLocalSearchText(event.target.value)}
              placeholder={t('localPanel.searchPlaceholder')}
              aria-label={t('localPanel.searchLabel')}
            />
            <button
              type="button"
              className="ghost-button"
              disabled={!localSearchText}
              onClick={() => {
                setLocalSearchText('');
                setDebouncedLocalSearchText('');
                setLocalSelection([]);
              }}
            >
              {t('common.clear')}
            </button>
          </div>
          {isLocalSearchActive && localSearchResultQuery.data ? (
            <p className="mono-cell">
              {t('localPanel.searchSummary', {
                total: localSearchResultQuery.data.total,
                scanned: localSearchResultQuery.data.scanned,
                truncated: localSearchResultQuery.data.truncated,
              })}
            </p>
          ) : null}
        </div>
      ) : null}
      <FileTable
        entries={activeEntries}
        selectedPaths={localSelection}
        currentPath={(isLocalSearchActive ? localSearchResultQuery.data?.current_path : listingQuery.data?.current_path) || currentPath}
        emptyMessage={
          isLocalSearchActive
            ? t('localPanel.searchEmpty')
            : isDirectLocalMode
              ? t('localPanel.localModeEmpty')
              : t('localPanel.empty')
        }
        isLoading={isLocalSearchActive ? localSearchResultQuery.isPending : listingQuery.isPending}
        errorMessage={
          isLocalSearchActive
            ? localSearchResultQuery.error
              ? getErrorMessage(localSearchResultQuery.error, t('localPanel.searchError'))
              : null
            : listingQuery.error
              ? getErrorMessage(listingQuery.error, t('localPanel.loadError'))
              : null
        }
        getEntrySubtitle={
          isLocalSearchActive
            ? (entry) => buildLocalSearchLocation(entry.path, entry.name, currentPath)
            : undefined
        }
        highlightQuery={isLocalSearchActive ? localSearchQuery : undefined}
        onSelect={(path, multi) => toggleLocalSelection(path, multi)}
        onSelectRange={setLocalSelection}
        onDeleteSelection={isDirectLocalMode ? undefined : handleDelete}
        onActivate={(entry) => {
          if (entry.is_dir) {
            setLocalPath(entry.path);
          }
        }}
        dragPayloadFactory={(entry) => ({
          kind: 'local',
          paths: localSelection.includes(entry.path) ? localSelection : [entry.path],
        })}
        onDropTransfer={(payload, targetPath) => {
          if (payload.kind !== 'remote') {
            return;
          }
          void onQueueDownloads(payload, targetPath);
        }}
      />
    </section>
  );
}
