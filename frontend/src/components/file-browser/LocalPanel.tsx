import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { getErrorMessage } from '../../api/http';
import { listLocalDrives, listLocalFiles } from '../../api/localFiles';
import type { TransferDragPayload } from '../../api/types';
import { useI18n } from '../../i18n';
import { useWorkspaceStore } from '../../store/workspace';
import { FileTable } from './FileTable';

interface LocalPanelProps {
  onQueueDownloads: (payload: TransferDragPayload, targetDir: string) => void | Promise<void>;
}

export function LocalPanel({ onQueueDownloads }: LocalPanelProps) {
  const localCurrentPath = useWorkspaceStore((state) => state.localCurrentPath);
  const localPathDraft = useWorkspaceStore((state) => state.localPathDraft);
  const localSelection = useWorkspaceStore((state) => state.localSelection);
  const setLocalPath = useWorkspaceStore((state) => state.setLocalPath);
  const setLocalPathDraft = useWorkspaceStore((state) => state.setLocalPathDraft);
  const toggleLocalSelection = useWorkspaceStore((state) => state.toggleLocalSelection);
  const { t } = useI18n();

  const drivesQuery = useQuery({
    queryKey: ['local-drives'],
    queryFn: listLocalDrives,
  });

  const listingQuery = useQuery({
    queryKey: ['local-list', localCurrentPath],
    queryFn: () => listLocalFiles(localCurrentPath),
    enabled: Boolean(localCurrentPath),
  });

  useEffect(() => {
    if (!listingQuery.data) {
      return;
    }
    if (listingQuery.data.current_path !== localCurrentPath) {
      setLocalPath(listingQuery.data.current_path);
    }
  }, [listingQuery.data, localCurrentPath, setLocalPath]);

  return (
    <section className="panel-shell">
      <header className="panel-header">
        <div>
          <h3>{t('localPanel.title')}</h3>
          <p>{t('localPanel.description')}</p>
        </div>
        <div className="panel-actions">
          <select
            className="panel-select"
            value={drivesQuery.data?.items.some((item) => item.path === localCurrentPath) ? localCurrentPath : ''}
            onChange={(event) => setLocalPath(event.target.value)}
          >
            <option value="">{t('localPanel.chooseDrive')}</option>
            {drivesQuery.data?.items.map((drive) => (
              <option key={drive.path} value={drive.path}>
                {drive.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              if (listingQuery.data?.parent_path) {
                setLocalPath(listingQuery.data.parent_path);
              }
            }}
            disabled={!listingQuery.data?.parent_path}
          >
            ..
          </button>
          <button type="button" className="ghost-button" onClick={() => listingQuery.refetch()}>
            {t('common.refresh')}
          </button>
        </div>
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
          placeholder={t('localPanel.pathPlaceholder')}
        />
      </div>
      <FileTable
        entries={listingQuery.data?.items ?? []}
        selectedPaths={localSelection}
        currentPath={listingQuery.data?.current_path || localCurrentPath}
        emptyMessage={t('localPanel.empty')}
        isLoading={listingQuery.isPending}
        errorMessage={listingQuery.error ? getErrorMessage(listingQuery.error, t('localPanel.loadError')) : null}
        onSelect={(path, multi) => toggleLocalSelection(path, multi)}
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
