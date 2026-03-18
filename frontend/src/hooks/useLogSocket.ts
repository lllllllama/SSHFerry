import { useEffect } from 'react';

import { ApiError } from '../api/http';
import { listLogs } from '../api/logs';
import { getLogSocketUrl, parseLogSocketMessage } from '../api/ws';
import { translate } from '../i18n';
import { useAuthStore } from '../store/auth';
import { useLogsStore } from '../store/logs';
import { useUiStore } from '../store/ui';

const POLL_INTERVAL_MS = 4000;
const RECONNECT_DELAY_MS = 2200;
const MAX_RECONNECT_BEFORE_POLLING = 3;

function getLogFeatureError(error: unknown): string | null {
  if (error instanceof ApiError && error.status === 404) {
    return translate('log.backendRestartRequired');
  }
  return null;
}

export function useLogSocket() {
  const token = useAuthStore((state) => state.token);
  const authReady = useAuthStore((state) => state.status === 'ready');
  const setSnapshot = useLogsStore((state) => state.setSnapshot);
  const setSocketStatus = useLogsStore((state) => state.setSocketStatus);
  const setSocketError = useLogsStore((state) => state.setSocketError);
  const pushToast = useUiStore((state) => state.pushToast);

  useEffect(() => {
    if (!authReady || !token) {
      return undefined;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pollTimer: number | null = null;
    let reconnectAttempts = 0;
    let disposed = false;
    let unsupportedBackend = false;

    const stopPolling = () => {
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const stopWithMissingFeature = (message: string) => {
      unsupportedBackend = true;
      setSocketStatus('error');
      setSocketError(message);
      stopPolling();
      if (socket && socket.readyState < WebSocket.CLOSING) {
        socket.close();
      }
      pushToast({
        tone: 'warning',
        title: translate('log.title'),
        message,
      });
    };

    const pollLogs = async () => {
      try {
        const snapshot = await listLogs();
        setSnapshot(snapshot.items, snapshot.total, snapshot.sequence);
      } catch (error) {
        const featureError = getLogFeatureError(error);
        if (featureError) {
          stopWithMissingFeature(featureError);
          return;
        }
        setSocketError(error instanceof Error ? error.message : translate('socket.logPollFailed'));
      }
    };

    const startPolling = () => {
      if (unsupportedBackend) {
        return;
      }
      setSocketStatus('polling');
      void pollLogs();
      if (!pollTimer) {
        pollTimer = window.setInterval(() => {
          void pollLogs();
        }, POLL_INTERVAL_MS);
      }
    };

    const connect = () => {
      if (disposed || unsupportedBackend) {
        return;
      }

      setSocketStatus(reconnectAttempts > 0 ? 'reconnecting' : 'connecting');
      socket = new WebSocket(getLogSocketUrl(token));

      socket.onopen = () => {
        reconnectAttempts = 0;
        stopPolling();
        setSocketStatus('connected');
        setSocketError(null);
      };

      socket.onmessage = (event) => {
        const payload = parseLogSocketMessage(event.data);
        if (!payload) {
          return;
        }

        if (payload.type === 'log_snapshot') {
          setSnapshot(payload.items, payload.total, payload.sequence);
          return;
        }

        setSocketError(payload.detail);
        pushToast({
          tone: 'warning',
          title: translate('socket.logChannelErrorTitle'),
          message: payload.detail,
        });
      };

      socket.onclose = () => {
        if (disposed || unsupportedBackend) {
          return;
        }
        reconnectAttempts += 1;
        if (reconnectAttempts >= MAX_RECONNECT_BEFORE_POLLING) {
          startPolling();
        }
        reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        if (!unsupportedBackend) {
          setSocketStatus('error');
          setSocketError(translate('socket.logWebsocketError'));
        }
      };
    };

    void (async () => {
      try {
        const snapshot = await listLogs();
        if (disposed) {
          return;
        }
        setSnapshot(snapshot.items, snapshot.total, snapshot.sequence);
        connect();
      } catch (error) {
        if (disposed) {
          return;
        }
        const featureError = getLogFeatureError(error);
        if (featureError) {
          stopWithMissingFeature(featureError);
          return;
        }
        setSocketError(error instanceof Error ? error.message : translate('socket.logPollFailed'));
        connect();
      }
    })();

    return () => {
      disposed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      stopPolling();
      if (socket && socket.readyState < WebSocket.CLOSING) {
        socket.close();
      }
      setSocketStatus('idle');
    };
  }, [authReady, pushToast, setSnapshot, setSocketError, setSocketStatus, token]);
}