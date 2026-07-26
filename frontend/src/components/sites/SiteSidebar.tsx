import { useEffect, useState, type MouseEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError, getErrorMessage } from '../../api/http';
import { checkConnection, closeSession, listSessions, openSession } from '../../api/sessions';
import { deleteSites, listSites } from '../../api/sites';
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
  const [selectedSiteNames, setSelectedSiteNames] = useState<string[]>([]);
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

  const deleteSitesMutation = useMutation({ mutationFn: deleteSites });
  const checkConnectionMutation = useMutation({ mutationFn: checkConnection });
  const openSessionMutation = useMutation({ mutationFn: openSession });
  const closeSessionMutation = useMutation({ mutationFn: closeSession });

  const siteItems = sitesQuery.data?.items ?? [];
  const selectedSiteSet = new Set(selectedSiteNames);
  const selectedSite = siteItems.find((site) => site.name === selectedSiteName) ?? null;
  const selectedSites = siteItems.filter((site) => selectedSiteSet.has(site.name));
  const hasMultiSiteSelection = selectedSites.length > 1;
  const activeSessionId = activePaneId || sessionsQuery.data?.items[0]?.session_id || null;
  const selectedSiteEndpoint = selectedSite ? `${selectedSite.username}@${selectedSite.host}:${selectedSite.port}` : '';
  const selectedSiteAuthSummary = selectedSite ? getAuthSummary(selectedSite) : '';
  const connectionResultTone: 'success' | 'warning' = connectionResult.every((item) => item.passed) ? 'success' : 'warning';

  useEffect(() => {
    if (!sitesQuery.data?.items) {
      return;
    }
    const availableNames = new Set(sitesQuery.data.items.map((site) => site.name));
    if (selectedSiteName && !availableNames.has(selectedSiteName)) {
      setSelectedSiteName(null);
    }
    setSelectedSiteNames((current) => {
      const next = current.filter((siteName) => availableNames.has(siteName));
      if (selectedSiteName && availableNames.has(selectedSiteName) && !next.includes(selectedSiteName)) {
        return [selectedSiteName];
      }
      return next.length === current.length ? current : next;
    });
  }, [selectedSiteName, setSelectedSiteName, sitesQuery.data?.items]);

  function needsRuntimeSecret(site: SiteResponse) {
    return site.auth_method === 'password' && !site.has_password;
  }

  function getAuthSummary(site: SiteResponse) {
    return site.auth_method === 'password'
      ? site.has_password
        ? t('siteSidebar.authSummarySavedPassword')
        : t('siteSidebar.authSummaryRuntimePassword')
      : t('siteSidebar.authSummaryKey');
  }

  async function handleCheck(site: SiteResponse, payload?: { password?: string; keyPassphrase?: string }) {
    try {
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
      return true;
    } catch (error) {
      pushToast({
        tone: 'danger',
        title: t('siteSidebar.toast.checkFailed', { siteName: site.name }),
        message: getErrorMessage(error),
      });
      return false;
    }
  }

  async function handleOpenSession(site: SiteResponse, payload?: { password?: string; keyPassphrase?: string }) {
    try {
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
      return true;
    } catch (error) {
      pushToast({
        tone: 'danger',
        title: t('siteSidebar.toast.sessionOpenFailed'),
        message: getErrorMessage(error),
      });
      return false;
    }
  }

  async function closeSingleSession(sessionId: string) {
    try {
      await closeSessionMutation.mutateAsync({ session_id: sessionId });
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) {
        pushToast({
          tone: 'danger',
          title: t('siteSidebar.toast.sessionCloseFailed'),
          message: getErrorMessage(error),
        });
        return;
      }
      // 404 means the backend no longer knows this session; treat it as already closed.
    }
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

  function selectSite(siteName: string, event: MouseEvent<HTMLButtonElement>) {
    const siteNames = siteItems.map((site) => site.name);
    let nextSelection: string[];
    let nextActiveSiteName: string | null = siteName;

    if (event.shiftKey && selectedSiteName) {
      const anchorIndex = siteNames.indexOf(selectedSiteName);
      const targetIndex = siteNames.indexOf(siteName);
      if (anchorIndex >= 0 && targetIndex >= 0) {
        const [start, end] = [anchorIndex, targetIndex].sort((a, b) => a - b);
        nextSelection = siteNames.slice(start, end + 1);
      } else {
        nextSelection = [siteName];
      }
    } else if (event.ctrlKey || event.metaKey) {
      if (selectedSiteNames.includes(siteName)) {
        nextSelection = selectedSiteNames.filter((value) => value !== siteName);
        nextActiveSiteName = selectedSiteName === siteName ? nextSelection.at(-1) ?? null : selectedSiteName;
      } else {
        nextSelection = [...selectedSiteNames, siteName];
      }
    } else {
      nextSelection = [siteName];
    }

    setSelectedSiteNames(nextSelection);
    setSelectedSiteName(nextActiveSiteName);
  }

  function requestDeleteSites(sites: SiteResponse[]) {
    const siteNames = sites.map((site) => site.name);
    const siteNameSet = new Set(siteNames);
    const affectedPanes = panes.filter((pane) => siteNameSet.has(pane.siteName)).map((pane) => pane.sessionId);
    const isBulkDelete = sites.length > 1;
    openConfirm({
      title: isBulkDelete
        ? t('siteSidebar.confirm.deleteSitesTitle', { count: sites.length })
        : t('siteSidebar.confirm.deleteSiteTitle', { siteName: siteNames[0] }),
      description: isBulkDelete
        ? t('siteSidebar.confirm.deleteSitesDescription', {
            count: affectedPanes.length,
            names: siteNames.join('\n'),
          })
        : t('siteSidebar.confirm.deleteSiteDescription', {
            siteName: siteNames[0],
            count: affectedPanes.length,
          }),
      confirmLabel: isBulkDelete ? t('siteSidebar.confirm.deleteSites') : t('siteSidebar.confirm.deleteSite'),
      destructive: true,
      onConfirm: async () => {
        const result = await deleteSitesMutation.mutateAsync(siteNames);
        affectedPanes.forEach((sessionId) => closePane(sessionId));
        if (selectedSiteName && siteNameSet.has(selectedSiteName)) {
          setSelectedSiteName(null);
        }
        setSelectedSiteNames((current) => current.filter((siteName) => !siteNameSet.has(siteName)));
        await queryClient.invalidateQueries({ queryKey: ['sites'] });
        await queryClient.invalidateQueries({ queryKey: ['sessions'] });
        pushToast({
          tone: 'success',
          title: isBulkDelete
            ? t('siteSidebar.toast.sitesDeleted', { count: result.deleted.length })
            : t('siteSidebar.toast.siteDeleted', { siteName: siteNames[0] }),
        });
      },
    });
  }

  async function handleSecretSubmit(payload: { password?: string; keyPassphrase?: string }) {
    if (!secretRequest) {
      return;
    }
    const succeeded = secretRequest.mode === 'check'
      ? await handleCheck(secretRequest.site, payload)
      : await handleOpenSession(secretRequest.site, payload);
    if (succeeded) {
      setSecretRequest(null);
    }
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
            disabled={!selectedSite || hasMultiSiteSelection}
            onClick={() => openSiteEditor(selectedSite)}
          >
            {t('common.edit')}
          </button>
          <button
            type="button"
            className="ghost-button site-action-button"
            disabled={!selectedSites.length}
            onClick={() => {
              if (selectedSites.length) {
                requestDeleteSites(selectedSites);
              }
            }}
          >
            {t('common.remove')}
          </button>
          <button
            type="button"
            className="ghost-button site-action-button"
            disabled={!selectedSite || hasMultiSiteSelection}
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
            disabled={!selectedSite || hasMultiSiteSelection}
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
          {siteItems.map((site) => {
            const endpoint = `${site.username}@${site.host}:${site.port}`;
            const isSelected = selectedSiteSet.has(site.name);
            return (
              <button
                type="button"
                key={site.name}
                className={`sidebar-row ${isSelected ? 'is-active' : ''} ${selectedSiteName === site.name ? 'is-current' : ''}`}
                aria-pressed={isSelected}
                onClick={(event) => selectSite(site.name, event)}
              >
                <span className="sidebar-row-copy">
                  <span className="sidebar-row-title" title={site.name}>{site.name}</span>
                  <span className="sidebar-meta mono-cell sidebar-truncate" title={endpoint}>{endpoint}</span>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {selectedSite ? (
        <section className="sidebar-section site-summary">
          <details className="sidebar-details">
            <summary className="sidebar-title-row sidebar-details-summary">
              <strong>{t('siteSidebar.selectedSite')}</strong>
              <StatusBadge tone="info">{formatProtocol(selectedSite.default_transfer_protocol)}</StatusBadge>
            </summary>
            <div className="sidebar-details-body">
              <p className="sidebar-truncate" title={selectedSiteEndpoint}>{selectedSiteEndpoint}</p>
              <p className="mono-cell sidebar-truncate" title={selectedSite.remote_root}>{selectedSite.remote_root}</p>
              <p className="sidebar-help sidebar-truncate" title={selectedSiteAuthSummary}>{selectedSiteAuthSummary}</p>
            </div>
          </details>
        </section>
      ) : null}

      <section className="sidebar-section">
        <div className="sidebar-title-row">
          <strong>{t('siteSidebar.openSessions')}</strong>
          <StatusBadge tone="neutral">{sessionsQuery.data?.total?.toString() || '0'}</StatusBadge>
        </div>
        <div className="sidebar-list">
          {sessionsQuery.data?.items.map((session) => {
            const sessionMeta = `${shortId(session.session_id)} / ${session.remote_root}`;
            return (
              <div key={session.session_id} className={`sidebar-row compact-session ${activePaneId === session.session_id ? 'is-active' : ''}`}>
                <button type="button" className="sidebar-row-main" onClick={() => setActivePane(session.session_id)}>
                  <span className="sidebar-row-copy">
                    <span className="sidebar-row-title" title={session.site_name}>{session.site_name}</span>
                    <span className="sidebar-meta mono-cell sidebar-truncate" title={sessionMeta}>{sessionMeta}</span>
                  </span>
                </button>
                <button type="button" className="row-action" onClick={() => requestCloseSession(session.session_id)}>
                  {t('common.close')}
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {connectionResult.length ? (
        <section className="sidebar-section result-card">
          <details className="sidebar-details">
            <summary className="sidebar-title-row sidebar-details-summary">
              <strong>{t('siteSidebar.connectionResult')}</strong>
              <StatusBadge tone={connectionResultTone}>{connectionResult.length.toString()}</StatusBadge>
            </summary>
            <div className="sidebar-details-body">
              {connectionResult.map((item) => {
                const line = t('siteSidebar.connectionLine', {
                  status: item.passed ? t('common.ok') : t('common.fail'),
                  name: item.name,
                  message: item.message,
                });
                return (
                  <p key={`${item.name}-${item.message}`} className="sidebar-truncate" title={line}>
                    {line}
                  </p>
                );
              })}
            </div>
          </details>
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
