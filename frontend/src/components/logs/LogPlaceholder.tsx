import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import { clearLogs } from '../../api/logs';
import { useI18n } from '../../i18n';
import { useLogsStore } from '../../store/logs';
import { useUiStore } from '../../store/ui';
import { StatusBadge } from '../common/StatusBadge';

interface LogPlaceholderProps {
  fullPage?: boolean;
}

function getLogTone(level: string) {
  if (level === 'ERROR' || level === 'CRITICAL') {
    return 'danger' as const;
  }
  if (level === 'WARNING') {
    return 'warning' as const;
  }
  if (level === 'INFO') {
    return 'info' as const;
  }
  return 'neutral' as const;
}

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

export function LogPlaceholder({ fullPage = false }: LogPlaceholderProps) {
  const items = useLogsStore((state) => state.items);
  const total = useLogsStore((state) => state.total);
  const socketStatus = useLogsStore((state) => state.socketStatus);
  const socketError = useLogsStore((state) => state.socketError);
  const pushToast = useUiStore((state) => state.pushToast);
  const listRef = useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const { formatDateTime, formatSocketStatus, t } = useI18n();

  const clearMutation = useMutation({ mutationFn: clearLogs });

  useEffect(() => {
    if (!autoScroll || !listRef.current) {
      return;
    }
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [autoScroll, items, fullPage]);

  return (
    <section className={`log-viewer ${fullPage ? 'log-viewer-full' : 'log-placeholder'} panel-shell`}>
      <header className="panel-header">
        <div>
          <h3>{t('log.title')}</h3>
          <p>{t(fullPage ? 'log.pageDescription' : 'log.description')}</p>
        </div>
        <div className="panel-actions">
          <StatusBadge tone={getSocketTone(socketStatus)}>{formatSocketStatus(socketStatus)}</StatusBadge>
        </div>
      </header>
      <div className="log-toolbar">
        <div className="log-toolbar-meta">
          <span className="mono-cell">{t('log.summary', { total })}</span>
          {socketError ? <span className="inline-error">{socketError}</span> : null}
        </div>
        <div className="log-toolbar-actions">
          <label className="log-auto-scroll">
            <input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} />
            {t('log.autoScroll')}
          </label>
          <button
            type="button"
            className="ghost-button"
            disabled={!total || clearMutation.isPending}
            onClick={() => {
              void clearMutation.mutateAsync().then(() => {
                pushToast({ tone: 'success', title: t('log.cleared') });
              });
            }}
          >
            {clearMutation.isPending ? t('common.processing') : t('log.clear')}
          </button>
        </div>
      </div>
      {fullPage ? (
        <div className="log-terminal-shell" ref={listRef}>
          {!items.length ? (
            <div className="table-state log-empty log-terminal-empty">
              <strong>{t('log.emptyTitle')}</strong>
              <p>{t('log.emptyBody')}</p>
            </div>
          ) : (
            items.map((item) => (
              <div key={item.sequence} className={`log-terminal-line is-${item.level.toLowerCase()}`}>
                {item.rendered}
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="log-viewer-body">
          {!items.length ? (
            <div className="table-state log-empty">
              <strong>{t('log.emptyTitle')}</strong>
              <p>{t('log.emptyBody')}</p>
            </div>
          ) : (
            <div className="log-list" ref={listRef}>
              {items.map((item) => (
                <article key={item.sequence} className="log-entry">
                  <div className="log-entry-head">
                    <span className="mono-cell">{formatDateTime(item.timestamp)}</span>
                    <StatusBadge tone={getLogTone(item.level)}>{item.level}</StatusBadge>
                    <span className="log-source mono-cell" title={item.logger}>
                      {item.logger}
                    </span>
                  </div>
                  <div className="log-message">{item.message}</div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}