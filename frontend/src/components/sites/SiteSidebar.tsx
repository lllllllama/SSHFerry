import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getErrorMessage } from '../../api/http';
import { checkConnection, closeSession, listSessions, openSession } from '../../api/sessions';
import { deleteSite, listSites } from '../../api/sites';
import type { ConnectionCheckResult, SiteResponse } from '../../api/types';
import { useI18n } from '../../i18n';
import { useTasksStore } from '../../store/tasks';
import { useUiStore } from '../../store/ui';
import { useWorkspaceStore } from '../../store/workspace';
import { shortId } from '../../utils/format';
import { StatusBadge } from '../common/StatusBadge';
import { SecretPromptDialog } from './SecretPromptDialog';

interface SecretRequestState {
  mode: 'check' | 'open';
  site: SiteResponse;
}

export function SiteSidebar() {
  const queryClient = useQueryClient();
  const selectedSiteName = useWorkspaceStore((state) => state.selectedSiteName);
  const panes = useWorkspaceStore((state) => state.panes);
  const activePaneId = useWorkspaceStore((state) => state.activePaneId);
  const setSelectedSiteName = useWorkspaceStore((state) => state.setSelectedSiteName);
  const setActivePane = useWorkspaceStore((state) => state.setActivePane);
  const closePane = useWorkspaceStore((state) => state.closePane);
  const protocolOverride = useUiStore((state) => state.protocolOverride);
  const setProtocolOverride = useUiStore((state) => state.setProtocolOverride);
  const openSiteEditor = useUiStore((state) => state.openSiteEditor);
  const openConfirm = useUiStore((state) => state.openConfirm);
  const pushToast = useUiStore((state) => state.pushToast);
  const tasks = useTasksStore((state) => state.items);
  const [secretRequest, setSecretRequest] = useState<SecretRequestState | null>(null);
  const [connectionResult, setConnectionResult] = useState<ConnectionCheckResult[]>([]);
  const { formatProtocol, t } = useI18n();

  const sitesQuery = useQuery({
    queryKey: ['sites'],
    queryFn: listSites,
  });

  const sessionsQuery = useQuery({
    queryKey: ['sessions'],
    queryFn: listSessions,
  });

  const deleteSiteMutation = useMutation({ mutationFn: deleteSite });
  const checkConnectionMutation = useMutation({ mutationFn: checkConnection });
  const openSessionMutation = useMutation({ mutationFn: openSession });
  const closeSessionMutation = useMutation({ mutationFn: closeSession });

  const selectedSite = sitesQuery.data?.items.find((site) => site.name === selectedSiteName) ?? null;
  const activeSessionId = activePaneId || sessionsQuery.data?.items[0]?.session_id || null;

  function needsRuntimeSecret(site: SiteResponse) {
    return site.auth_method === 'password' && !site.has_password;
  }

  async function handleCheck(site: SiteResponse, payload?: { password?: string; keyPassphrase?: string }) {
    const result = await checkConnectionMutation.mutateAsync({
      site_name: site.name,
      password: payload?.password || null,
      key_passphrase: payload?.keyPassphrase || null,
    });
    setConnectionResult(result.results);
    pushToast({
      tone: result.all_passed ? 'success' : 'warning',
      title: t('siteSidebar.toast.checkComplete', { siteName: site.name }),
    });
  }

  async function handleOpenSession(site: SiteResponse, payload?: { password?: string; keyPassphrase?: string }) {
    const session = await openSessionMutation.mutateAsync({
      site_name: site.name,
      password: payload?.password || null,
      key_passphrase: payload?.keyPassphrase || null,
    });
    useWorkspaceStore.getState().upsertPane(session);
    await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    pushToast({
      tone: 'success',
      title: t('siteSidebar.toast.sessionOpened'),
      message: t('siteSidebar.toast.sessionOpenedMessage', {
        siteName: session.site_name,
        sessionId: shortId(session.session_id),
      }),
    });
  }

  async function closeSingleSession(sessionId: string) {
    await closeSessionMutation.mutateAsync({ session_id: sessionId });
    closePane(sessionId);
    await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    pushToast({ tone: 'success', title: t('siteSidebar.toast.sessionClosed') });
  }

  function requestCloseSession(sessionId: string) {
    const hasRunningTask = tasks.some(
      (task) => !task.is_finished && (task.src_session_id === sessionId || task.dst_session_id === sessionId),
    );
    if (!hasRunningTask) {
      void closeSingleSession(sessionId);
      return;
    }
    openConfirm({
      title: t('siteSidebar.confirm.closeSessionTitle'),
      description: t('siteSidebar.confirm.closeSessionDescription', { sessionId: shortId(sessionId) }),
      confirmLabel: t('siteSidebar.confirm.closeSession'),
      destructive: true,
      onConfirm: () => closeSingleSession(sessionId),
    });
  }

  function requestDeleteSite(site: SiteResponse) {
    const affectedPanes = panes.filter((pane) => pane.siteName === site.name).map((pane) => pane.sessionId);
    openConfirm({
      title: t('siteSidebar.confirm.deleteSiteTitle', { siteName: site.name }),
      description: t('siteSidebar.confirm.deleteSiteDescription', {
        siteName: site.name,
        count: affectedPanes.length,
      }),
      confirmLabel: t('siteSidebar.confirm.deleteSite'),
      destructive: true,
      onConfirm: async () => {
        await deleteSiteMutation.mutateAsync(site.name);
        affectedPanes.forEach((sessionId) => closePane(sessionId));
        if (selectedSiteName === site.name) {
          setSelectedSiteName(null);
        }
        await queryClient.invalidateQueries({ queryKey: ['sites'] });
        await queryClient.invalidateQueries({ queryKey: ['sessions'] });
        pushToast({ tone: 'success', title: t('siteSidebar.toast.siteDeleted', { siteName: site.name }) });
      },
    });
  }

  async function handleSecretSubmit(payload: { password?: string; keyPassphrase?: string }) {
    if (!secretRequest) {
      return;
    }
    if (secretRequest.mode === 'check') {
      await handleCheck(secretRequest.site, payload);
    } else {
      await handleOpenSession(secretRequest.site, payload);
    }
    setSecretRequest(null);
  }

  return (
    <aside className="panel-shell sidebar-shell">
      <header className="panel-header">
        <div>
          <h3>{t('siteSidebar.title')}</h3>
          <p>{t('siteSidebar.description')}</p>
        </div>
      </header>

      <section className="sidebar-section">
        <div className="sidebar-action-grid">
          <button type="button" className="ghost-button site-action-button" onClick={() => openSiteEditor(null)}>
            {t('common.add')}
          </button>
          <button
            type="button"
            className="ghost-button site-action-button"
            disabled={!selectedSite}
            onClick={() => openSiteEditor(selectedSite)}
          >
            {t('common.edit')}
          </button>
          <button
            type="button"
            className="ghost-button site-action-button"
            disabled={!selectedSite}
            onClick={() => {
              if (selectedSite) {
                requestDeleteSite(selectedSite);
              }
            }}
          >
            {t('common.remove')}
          </button>
          <button
            type="button"
            className="ghost-button site-action-button"
            disabled={!selectedSite}
            onClick={() => {
              if (!selectedSite) {
                return;
              }
              if (needsRuntimeSecret(selectedSite)) {
                setSecretRequest({ mode: 'check', site: selectedSite });
                return;
              }
              void handleCheck(selectedSite);
            }}
          >
            {t('common.check')}
          </button>
          <button
            type="button"
            className="ghost-button site-action-button site-action-span-2"
            disabled={!selectedSite}
            onClick={() => {
              if (!selectedSite) {
                return;
              }
              if (needsRuntimeSecret(selectedSite)) {
                setSecretRequest({ mode: 'open', site: selectedSite });
                return;
              }
              void handleOpenSession(selectedSite);
            }}
          >
            {t('siteSidebar.secretOpenSubmit')}
          </button>
          <button
            type="button"
            className="ghost-button site-action-button site-action-span-2"
            disabled={!activeSessionId}
            onClick={() => {
              if (activeSessionId) {
                requestCloseSession(activeSessionId);
              }
            }}
          >
            {t('siteSidebar.closeSession')}
          </button>
        </div>
      </section>

      <section className="sidebar-section">
        <label className="form-field">
          <span>{t('siteSidebar.protocolOverride')}</span>
          <select value={protocolOverride} onChange={(event) => setProtocolOverride(event.target.value as 'auto' | 'sftp' | 'scp')}>
            <option value="auto">{formatProtocol('auto')}</option>
            <option value="sftp">{formatProtocol('sftp')}</option>
            <option value="scp">{formatProtocol('scp')}</option>
          </select>
        </label>
      </section>

      <section className="sidebar-section">
        <div className="sidebar-title-row">
          <strong>{t('siteSidebar.sites')}</strong>
          <StatusBadge tone="neutral">{sitesQuery.data?.total?.toString() || '0'}</StatusBadge>
        </div>
        <div className="sidebar-list">
          {sitesQuery.data?.items.map((site) => (
            <button
              type="button"
              key={site.name}
              className={`sidebar-row ${selectedSiteName === site.name ? 'is-active' : ''}`}
              onClick={() => setSelectedSiteName(site.name)}
            >
              <span>{site.name}</span>
              <span className="sidebar-meta mono-cell">{site.username}@{site.host}:{site.port}</span>
            </button>
          ))}
        </div>
      </section>

      {selectedSite ? (
        <section className="sidebar-section site-summary">
          <div className="sidebar-title-row">
            <strong>{t('siteSidebar.selectedSite')}</strong>
            <StatusBadge tone="info">{formatProtocol(selectedSite.default_transfer_protocol)}</StatusBadge>
          </div>
          <p>{selectedSite.username}@{selectedSite.host}:{selectedSite.port}</p>
          <p className="mono-cell">{selectedSite.remote_root}</p>
          <p className="sidebar-help">
            {selectedSite.auth_method === 'password'
              ? selectedSite.has_password
                ? t('siteSidebar.authSummarySavedPassword')
                : t('siteSidebar.authSummaryRuntimePassword')
              : t('siteSidebar.authSummaryKey')}
          </p>
        </section>
      ) : null}

      <section className="sidebar-section">
        <div className="sidebar-title-row">
          <strong>{t('siteSidebar.openSessions')}</strong>
          <StatusBadge tone="neutral">{sessionsQuery.data?.total?.toString() || '0'}</StatusBadge>
        </div>
        <div className="sidebar-list">
          {sessionsQuery.data?.items.map((session) => (
            <div key={session.session_id} className={`sidebar-row compact-session ${activePaneId === session.session_id ? 'is-active' : ''}`}>
              <button type="button" className="sidebar-row-main" onClick={() => setActivePane(session.session_id)}>
                <span>{session.site_name}</span>
                <span className="sidebar-meta mono-cell">{shortId(session.session_id)} · {session.remote_root}</span>
              </button>
              <button type="button" className="row-action" onClick={() => requestCloseSession(session.session_id)}>
                {t('common.close')}
              </button>
            </div>
          ))}
        </div>
      </section>

      {connectionResult.length ? (
        <section className="sidebar-section result-card">
          <div className="sidebar-title-row">
            <strong>{t('siteSidebar.connectionResult')}</strong>
          </div>
          {connectionResult.map((item) => (
            <p key={`${item.name}-${item.message}`}>
              {t('siteSidebar.connectionLine', {
                status: item.passed ? t('common.ok') : t('common.fail'),
                name: item.name,
                message: item.message,
              })}
            </p>
          ))}
        </section>
      ) : null}

      {sitesQuery.error || sessionsQuery.error ? (
        <section className="sidebar-section inline-error">
          {getErrorMessage(sitesQuery.error || sessionsQuery.error, t('siteSidebar.loadError'))}
        </section>
      ) : null}

      <SecretPromptDialog
        open={Boolean(secretRequest)}
        site={secretRequest?.site ?? null}
        title={secretRequest?.mode === 'check' ? t('siteSidebar.secretCheckTitle') : t('siteSidebar.secretOpenTitle')}
        submitLabel={secretRequest?.mode === 'check' ? t('siteSidebar.secretCheckSubmit') : t('siteSidebar.secretOpenSubmit')}
        onClose={() => setSecretRequest(null)}
        onSubmit={handleSecretSubmit}
      />
    </aside>
  );
}
