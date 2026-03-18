import { useI18n } from '../../i18n';
import type { RemotePaneState } from '../../store/workspace';
import { RemotePane } from './RemotePane';

interface RemoteWorkspaceProps {
  panes: RemotePaneState[];
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

export function RemoteWorkspace({
  panes,
  onCloseSession,
  onQueueUploads,
  onQueueDownloads,
  onQueueRemoteCopies,
}: RemoteWorkspaceProps) {
  const { t } = useI18n();

  if (!panes.length) {
    return (
      <section className="panel-shell remote-workspace-empty remote-workspace-shell">
        <header className="panel-header">
          <div>
            <h3>{t('remoteWorkspace.title')}</h3>
            <p>{t('remoteWorkspace.description')}</p>
          </div>
        </header>
        <div className="placeholder-body">
          <strong>{t('remoteWorkspace.emptyTitle')}</strong>
          <p>{t('remoteWorkspace.emptyBody')}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="remote-workspace-grid remote-workspace-shell">
      {panes.map((pane) => (
        <RemotePane
          key={pane.sessionId}
          pane={pane}
          onCloseSession={onCloseSession}
          onQueueUploads={onQueueUploads}
          onQueueDownloads={onQueueDownloads}
          onQueueRemoteCopies={onQueueRemoteCopies}
        />
      ))}
    </section>
  );
}
