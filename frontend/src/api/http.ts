import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { useAuthStore } from '../store/auth';
import { useUiStore } from '../store/ui';
import { translate } from '../i18n';

export class ApiError extends Error {
  status?: number;

  detail: string;

  constructor(detail: string, status?: number) {
    super(detail);
    this.name = 'ApiError';
    this.detail = detail;
    this.status = status;
  }
}

const DEFAULT_HTTP_URL = 'http://127.0.0.1:18080';

export const http = axios.create({
  baseURL: import.meta.env.VITE_BACKEND_HTTP_URL ?? DEFAULT_HTTP_URL,
  timeout: 20000,
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const { token, headerName } = useAuthStore.getState();
  if (token) {
    config.headers.set(headerName || 'X-SSHFerry-Token', token);
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string }>) => {
    const detail = error.response?.data?.detail || error.message || translate('http.requestFailed');
    const apiError = new ApiError(detail, error.response?.status);

    if (apiError.status === 401) {
      useAuthStore.getState().setInitError(translate('http.sessionInvalid'));
    }
    if (apiError.status === 503) {
      useUiStore.getState().pushToast({
        tone: 'warning',
        title: translate('http.backendNotReadyTitle'),
        message: translate('http.backendNotReadyMessage'),
      });
    }

    return Promise.reject(apiError);
  },
);

export function getErrorMessage(error: unknown, fallback = translate('http.requestFailed')): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
