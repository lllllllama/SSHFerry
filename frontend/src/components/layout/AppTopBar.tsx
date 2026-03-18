import { Link, useLocation } from 'react-router-dom';

import { useI18n } from '../../i18n';
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
  const { formatProtocol, formatSocketStatus, language, setLanguage, t } = useI18n();

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <strong>SSHFerry</strong>
        <span>{t('topbar.tagline')}</span>
      </div>
      <div className="topbar-statuses">
        <div className="topbar-status-item">
          <span>{t('topbar.backend')}</span>
          <StatusBadge tone={health?.ready ? 'success' : 'warning'}>
            {health?.ready ? t('common.ready') : t('common.booting')}
          </StatusBadge>
        </div>
        <div className="topbar-status-item">
          <span>{t('topbar.taskChannel')}</span>
          <StatusBadge tone={getSocketTone(socketStatus)}>{formatSocketStatus(socketStatus)}</StatusBadge>
        </div>
        <div className="topbar-status-item">
          <span>{t('topbar.protocol')}</span>
          <StatusBadge tone={protocolOverride === 'auto' ? 'neutral' : 'info'}>{formatProtocol(protocolOverride)}</StatusBadge>
        </div>
      </div>
      <div className="topbar-controls">
        <div className="locale-switch" role="group" aria-label={t('topbar.language')}>
          <button
            type="button"
            className={`locale-button ${language === 'zh' ? 'is-active' : ''}`}
            onClick={() => setLanguage('zh')}
          >
            {t('language.zh')}
          </button>
          <button
            type="button"
            className={`locale-button ${language === 'en' ? 'is-active' : ''}`}
            onClick={() => setLanguage('en')}
          >
            {t('language.en')}
          </button>
        </div>
        <nav className="topbar-nav">
          <Link className={location.pathname === '/workspace' ? 'nav-link active' : 'nav-link'} to="/workspace">
            {t('nav.workspace')}
          </Link>
          <Link className={location.pathname === '/tasks' ? 'nav-link active' : 'nav-link'} to="/tasks">
            {t('nav.tasks')}
          </Link>
        </nav>
      </div>
    </header>
  );
}
