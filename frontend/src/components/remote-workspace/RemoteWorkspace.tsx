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
  if (!panes.length) {
    return (
      <section className="panel-shell remote-workspace-empty">
        <header className="panel-header">
          <div>
            <h3>Remote Workspace</h3>
            <p>多 session 并排工作区。</p>
          </div>
        </header>
        <div className="placeholder-body">
          <strong>No remote sessions open</strong>
          <p>从左侧选择站点并打开 session，远端 pane 会按顺序追加到右侧。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="remote-workspace-grid">
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
