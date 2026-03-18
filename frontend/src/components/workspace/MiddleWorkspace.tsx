import type { TransferDragPayload } from '../../api/types';
import { useI18n } from '../../i18n';
import type { CenterPanelMode, RemotePaneState } from '../../store/workspace';
import { LocalPanel } from '../file-browser/LocalPanel';
import { RemotePane } from '../remote-workspace/RemotePane';

interface MiddleWorkspaceProps {
  panes: RemotePaneState[];
  mode: CenterPanelMode;
  centerSessionId: string | null;
  onChangeMode: (mode: CenterPanelMode) => void;
  onChangeSessionId: (sessionId: string | null) => void;
  onQueueLocalDownloads: (payload: TransferDragPayload, targetDir: string) => void | Promise<void>;
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

export function MiddleWorkspace({
  panes,
  mode,
  centerSessionId,
  onChangeMode,
  onChangeSessionId,
  onQueueLocalDownloads,
  onCloseSession,
  onQueueUploads,
  onQueueDownloads,
  onQueueRemoteCopies,
}: MiddleWorkspaceProps) {
  const { t } = useI18n();
  const canUseRemote = panes.length > 0;
  const effectiveMode = mode === 'remote' && canUseRemote ? 'remote' : 'local';
  const centerPane = panes.find((pane) => pane.sessionId === centerSessionId) ?? panes[0] ?? null;

  return (
    <section className="middle-workspace">
      <div className="panel-shell middle-panel-switch">
        <div className="middle-panel-switch-row">
          <div className="middle-panel-switch-copy">
            <strong>{t('workspace.middlePanelMode')}</strong>
            <p>{t('workspace.middlePanelDescription')}</p>
          </div>
          <div className="middle-panel-toggle" role="group" aria-label={t('workspace.middlePanelMode')}>
            <button
              type="button"
              className={`middle-panel-button ${effectiveMode === 'local' ? 'is-active' : ''}`}
              onClick={() => onChangeMode('local')}
            >
              {t('endpoint.local')}
            </button>
            <button
              type="button"
              className={`middle-panel-button ${effectiveMode === 'remote' ? 'is-active' : ''}`}
              onClick={() => onChangeMode('remote')}
              disabled={!canUseRemote}
            >
              {t('endpoint.remote')}
            </button>
          </div>
        </div>
        {effectiveMode === 'remote' ? (
          <label className="form-field middle-panel-select">
            <span>{t('workspace.middleSession')}</span>
            <select
              value={centerPane?.sessionId ?? ''}
              onChange={(event) => onChangeSessionId(event.target.value || null)}
            >
              {panes.map((pane) => (
                <option key={pane.sessionId} value={pane.sessionId}>
                  {pane.siteName} · {pane.currentPath}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      {effectiveMode === 'local' ? (
        <LocalPanel onQueueDownloads={onQueueLocalDownloads} />
      ) : centerPane ? (
        <RemotePane
          pane={centerPane}
          onCloseSession={onCloseSession}
          onQueueUploads={onQueueUploads}
          onQueueDownloads={onQueueDownloads}
          onQueueRemoteCopies={onQueueRemoteCopies}
        />
      ) : (
        <section className="panel-shell remote-workspace-empty">
          <div className="placeholder-body">
            <strong>{t('workspace.middleRemoteEmptyTitle')}</strong>
            <p>{t('workspace.middleRemoteEmptyBody')}</p>
          </div>
        </section>
      )}
    </section>
  );
}
