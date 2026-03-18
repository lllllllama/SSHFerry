import { Link, useLocation } from 'react-router-dom';

import { useAuthStore } from '../../store/auth';
import { useTasksStore } from '../../store/tasks';
import { useUiStore } from '../../store/ui';
import { StatusBadge } from '../common/StatusBadge';

function getSocketTone(status: string) {
  if (status === 'connected') {
    return 'success' as const;
  }
  if (status === 'polling' || status === 'reconnecting') {
    return 'warning' as const;
  }
  if (status === 'error') {
    return 'danger' as const;
  }
  return 'neutral' as const;
}

export function AppTopBar() {
  const location = useLocation();
  const health = useAuthStore((state) => state.health);
  const socketStatus = useTasksStore((state) => state.socketStatus);
  const protocolOverride = useUiStore((state) => state.protocolOverride);

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <strong>SSHFerry</strong>
        <span>本地化多会话传输工作台</span>
      </div>
      <div className="topbar-statuses">
        <div className="topbar-status-item">
          <span>Backend</span>
          <StatusBadge tone={health?.ready ? 'success' : 'warning'}>
            {health?.ready ? 'Ready' : 'Booting'}
          </StatusBadge>
        </div>
        <div className="topbar-status-item">
          <span>Task WS</span>
          <StatusBadge tone={getSocketTone(socketStatus)}>{socketStatus}</StatusBadge>
        </div>
        <div className="topbar-status-item">
          <span>Protocol</span>
          <StatusBadge tone={protocolOverride === 'auto' ? 'neutral' : 'info'}>
            {protocolOverride.toUpperCase()}
          </StatusBadge>
        </div>
      </div>
      <nav className="topbar-nav">
        <Link className={location.pathname === '/workspace' ? 'nav-link active' : 'nav-link'} to="/workspace">
          Workspace
        </Link>
        <Link className={location.pathname === '/tasks' ? 'nav-link active' : 'nav-link'} to="/tasks">
          Tasks
        </Link>
      </nav>
    </header>
  );
}
