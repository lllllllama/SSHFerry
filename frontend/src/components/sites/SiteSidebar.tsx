import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getErrorMessage } from '../../api/http';
import { checkConnection, closeSession, listSessions, openSession } from '../../api/sessions';
import { deleteSite, listSites } from '../../api/sites';
import type { SiteResponse } from '../../api/types';
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
  const [connectionResult, setConnectionResult] = useState<string[]>([]);

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
    setConnectionResult(result.results.map((item) => `${item.passed ? 'OK' : 'FAIL'} · ${item.name} · ${item.message}`));
    pushToast({
      tone: result.all_passed ? 'success' : 'warning',
      title: `连接检查完成: ${site.name}`,
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
      title: '远端会话已打开',
      message: `${session.site_name} · ${shortId(session.session_id)}`,
    });
  }

  async function closeSingleSession(sessionId: string) {
    await closeSessionMutation.mutateAsync({ session_id: sessionId });
    closePane(sessionId);
    await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    pushToast({ tone: 'success', title: '远端会话已关闭' });
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
      title: '关闭仍有关联任务的 Session',
      description: `Session ${shortId(sessionId)} 仍有关联中的任务。继续关闭会让当前 pane 失去上下文。`,
      confirmLabel: '继续关闭',
      destructive: true,
      onConfirm: () => closeSingleSession(sessionId),
    });
  }

  function requestDeleteSite(site: SiteResponse) {
    const affectedPanes = panes.filter((pane) => pane.siteName === site.name).map((pane) => pane.sessionId);
    openConfirm({
      title: `删除站点 ${site.name}`,
      description: `将删除站点 ${site.name}，并关闭 ${affectedPanes.length} 个引用它的当前会话。`,
      confirmLabel: '删除站点',
      destructive: true,
      onConfirm: async () => {
        await deleteSiteMutation.mutateAsync(site.name);
        affectedPanes.forEach((sessionId) => closePane(sessionId));
        if (selectedSiteName === site.name) {
          setSelectedSiteName(null);
        }
        await queryClient.invalidateQueries({ queryKey: ['sites'] });
        await queryClient.invalidateQueries({ queryKey: ['sessions'] });
        pushToast({ tone: 'success', title: `站点 ${site.name} 已删除` });
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
          <h3>Sites / Sessions</h3>
          <p>左侧主操作区，保留站点管理与全局控制。</p>
        </div>
      </header>

      <section className="sidebar-section">
        <div className="inline-actions wrap-actions">
          <button type="button" className="primary-button" onClick={() => openSiteEditor(null)}>
            Add
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={!selectedSite}
            onClick={() => openSiteEditor(selectedSite)}
          >
            Edit
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={!selectedSite}
            onClick={() => {
              if (selectedSite) {
                requestDeleteSite(selectedSite);
              }
            }}
          >
            Remove
          </button>
          <button
            type="button"
            className="ghost-button"
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
            Check
          </button>
          <button
            type="button"
            className="ghost-button"
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
            Open Session
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={!activeSessionId}
            onClick={() => {
              if (activeSessionId) {
                requestCloseSession(activeSessionId);
              }
            }}
          >
            Close Session
          </button>
        </div>
      </section>

      <section className="sidebar-section">
        <label className="form-field">
          <span>Task Protocol Override</span>
          <select value={protocolOverride} onChange={(event) => setProtocolOverride(event.target.value as 'auto' | 'sftp' | 'scp')}>
            <option value="auto">Auto</option>
            <option value="sftp">SFTP</option>
            <option value="scp">SCP</option>
          </select>
        </label>
      </section>

      <section className="sidebar-section">
        <div className="sidebar-title-row">
          <strong>Sites</strong>
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
            <strong>Selected Site</strong>
            <StatusBadge tone="info">{selectedSite.default_transfer_protocol}</StatusBadge>
          </div>
          <p>{selectedSite.username}@{selectedSite.host}:{selectedSite.port}</p>
          <p className="mono-cell">{selectedSite.remote_root}</p>
          <p className="sidebar-help">
            {selectedSite.auth_method === 'password'
              ? selectedSite.has_password
                ? '后端已保存密码，可直接开会话。'
                : '密码未保存，打开或检查时会要求输入运行时密码。'
              : '使用私钥认证，密钥路径与高级 SSH 选项保存在站点配置中。'}
          </p>
        </section>
      ) : null}

      <section className="sidebar-section">
        <div className="sidebar-title-row">
          <strong>Open Sessions</strong>
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
                关
              </button>
            </div>
          ))}
        </div>
      </section>

      {connectionResult.length ? (
        <section className="sidebar-section result-card">
          <div className="sidebar-title-row">
            <strong>Connection Result</strong>
          </div>
          {connectionResult.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </section>
      ) : null}

      {(sitesQuery.error || sessionsQuery.error) ? (
        <section className="sidebar-section inline-error">
          {getErrorMessage(sitesQuery.error || sessionsQuery.error, '站点侧栏加载失败')}
        </section>
      ) : null}

      <SecretPromptDialog
        open={Boolean(secretRequest)}
        site={secretRequest?.site ?? null}
        title={secretRequest?.mode === 'check' ? '运行时凭据: 连接检查' : '运行时凭据: 打开会话'}
        submitLabel={secretRequest?.mode === 'check' ? '开始检查' : '打开会话'}
        onClose={() => setSecretRequest(null)}
        onSubmit={handleSecretSubmit}
      />
    </aside>
  );
}
