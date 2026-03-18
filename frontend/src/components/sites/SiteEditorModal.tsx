import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { createSite, updateSite } from '../../api/sites';
import type { SiteResponse, SiteUpsertRequest } from '../../api/types';
import { useI18n } from '../../i18n';
import { useUiStore } from '../../store/ui';
import { useWorkspaceStore } from '../../store/workspace';
import { parseBasicSshCommand } from '../../utils/sshImport';
import { Modal } from '../common/Modal';

interface SiteFormState {
  name: string;
  host: string;
  port: number;
  username: string;
  remoteRoot: string;
  defaultTransferProtocol: 'sftp' | 'scp';
  authMethod: 'password' | 'key';
  password: string;
  keyPath: string;
  keyPassphrase: string;
  rememberPassword: boolean;
  proxyJump: string;
  sshConfigPath: string;
  sshOptionsText: string;
  sshCommand: string;
}

function toFormState(site: SiteResponse | null): SiteFormState {
  return {
    name: site?.name ?? '',
    host: site?.host ?? '',
    port: site?.port ?? 22,
    username: site?.username ?? '',
    remoteRoot: site?.remote_root ?? '/',
    defaultTransferProtocol: site?.default_transfer_protocol ?? 'sftp',
    authMethod: site?.auth_method ?? 'password',
    password: '',
    keyPath: site?.key_path ?? '',
    keyPassphrase: '',
    rememberPassword: site?.remember_password ?? false,
    proxyJump: site?.proxy_jump ?? '',
    sshConfigPath: site?.ssh_config_path ?? '',
    sshOptionsText: site?.ssh_options?.join('\n') ?? '',
    sshCommand: '',
  };
}

function toPayload(form: SiteFormState): SiteUpsertRequest {
  return {
    name: form.name.trim(),
    host: form.host.trim(),
    port: Number(form.port) || 22,
    username: form.username.trim(),
    auth_method: form.authMethod,
    remote_root: form.remoteRoot.trim() || '/',
    password: form.authMethod === 'password' ? form.password || null : null,
    key_path: form.authMethod === 'key' ? form.keyPath.trim() || null : null,
    key_passphrase: form.authMethod === 'key' ? form.keyPassphrase || null : null,
    remember_password: form.authMethod === 'password' ? form.rememberPassword : false,
    proxy_jump: form.proxyJump.trim() || null,
    ssh_config_path: form.sshConfigPath.trim() || null,
    ssh_options: form.sshOptionsText
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean),
    default_transfer_protocol: form.defaultTransferProtocol,
  };
}

export function SiteEditorModal() {
  const queryClient = useQueryClient();
  const siteEditor = useUiStore((state) => state.siteEditor);
  const closeSiteEditor = useUiStore((state) => state.closeSiteEditor);
  const pushToast = useUiStore((state) => state.pushToast);
  const setSelectedSiteName = useWorkspaceStore((state) => state.setSelectedSiteName);
  const [form, setForm] = useState<SiteFormState>(toFormState(null));
  const [parseError, setParseError] = useState(false);
  const { formatAuthMethod, formatProtocol, t } = useI18n();

  const mutation = useMutation({
    mutationFn: async (payload: SiteUpsertRequest) => {
      if (siteEditor.site) {
        return updateSite(siteEditor.site.name, payload);
      }
      return createSite(payload);
    },
    onSuccess: async (site) => {
      await queryClient.invalidateQueries({ queryKey: ['sites'] });
      setSelectedSiteName(site.name);
      pushToast({
        tone: 'success',
        title: siteEditor.site ? t('siteEditor.toast.updated') : t('siteEditor.toast.created'),
        message: t('siteEditor.toast.savedMessage', { siteName: site.name }),
      });
      closeSiteEditor();
    },
  });

  useEffect(() => {
    if (!siteEditor.open) {
      return;
    }
    setForm(toFormState(siteEditor.site));
    setParseError(false);
  }, [siteEditor.open, siteEditor.site]);

  function patchForm(next: Partial<SiteFormState>) {
    setForm((current) => ({ ...current, ...next }));
  }

  function handleParseCommand() {
    const parsed = parseBasicSshCommand(form.sshCommand);
    if (!parsed) {
      setParseError(true);
      return;
    }
    patchForm({
      host: parsed.host,
      port: parsed.port ?? form.port,
      username: parsed.username ?? form.username,
      name: form.name || parsed.name || form.name,
    });
    setParseError(false);
  }

  return (
    <Modal
      open={siteEditor.open}
      title={siteEditor.site ? t('siteEditor.editTitle') : t('siteEditor.newTitle')}
      description={t('siteEditor.description')}
      onClose={closeSiteEditor}
      width="wide"
      footer={
        <>
          <button type="button" className="ghost-button" onClick={closeSiteEditor}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={mutation.isPending}
            onClick={() => {
              void mutation.mutateAsync(toPayload(form));
            }}
          >
            {mutation.isPending ? t('common.saving') : t('common.save')}
          </button>
        </>
      }
    >
      <form className="site-editor-grid" onSubmit={(event) => event.preventDefault()}>
        <section className="editor-section">
          <div className="editor-section-title">{t('siteEditor.quickImport')}</div>
          <div className="inline-form-row">
            <input
              value={form.sshCommand}
              onChange={(event) => patchForm({ sshCommand: event.target.value })}
              placeholder="ssh -p 16921 root@example.com"
            />
            <button type="button" className="ghost-button" onClick={handleParseCommand}>
              {t('common.parse')}
            </button>
          </div>
          {parseError ? <p className="inline-error">{t('siteEditor.parseError')}</p> : null}
        </section>

        <section className="editor-grid-two">
          <label className="form-field">
            <span>{t('siteEditor.siteName')}</span>
            <input value={form.name} onChange={(event) => patchForm({ name: event.target.value })} />
          </label>
          <label className="form-field">
            <span>{t('siteEditor.host')}</span>
            <input value={form.host} onChange={(event) => patchForm({ host: event.target.value })} />
          </label>
          <label className="form-field">
            <span>{t('siteEditor.port')}</span>
            <input
              type="number"
              min={1}
              max={65535}
              value={form.port}
              onChange={(event) => patchForm({ port: Number(event.target.value) })}
            />
          </label>
          <label className="form-field">
            <span>{t('siteEditor.username')}</span>
            <input value={form.username} onChange={(event) => patchForm({ username: event.target.value })} />
          </label>
          <label className="form-field form-field-full">
            <span>{t('siteEditor.remoteRoot')}</span>
            <input value={form.remoteRoot} onChange={(event) => patchForm({ remoteRoot: event.target.value })} />
          </label>
          <label className="form-field">
            <span>{t('siteEditor.defaultProtocol')}</span>
            <select
              value={form.defaultTransferProtocol}
              onChange={(event) => patchForm({ defaultTransferProtocol: event.target.value as 'sftp' | 'scp' })}
            >
              <option value="sftp">{formatProtocol('sftp')}</option>
              <option value="scp">{formatProtocol('scp')}</option>
            </select>
          </label>
          <label className="form-field">
            <span>{t('siteEditor.authMethod')}</span>
            <select
              value={form.authMethod}
              onChange={(event) => patchForm({ authMethod: event.target.value as 'password' | 'key' })}
            >
              <option value="password">{formatAuthMethod('password')}</option>
              <option value="key">{formatAuthMethod('key')}</option>
            </select>
          </label>
        </section>

        {form.authMethod === 'password' ? (
          <section className="editor-grid-two">
            <label className="form-field form-field-full">
              <span>{t('siteEditor.password')}</span>
              <input
                type="password"
                value={form.password}
                onChange={(event) => patchForm({ password: event.target.value })}
                placeholder={siteEditor.site?.has_password ? t('siteEditor.passwordPlaceholderSaved') : t('siteEditor.passwordPlaceholderNew')}
              />
            </label>
            <label className="checkbox-field form-field-full">
              <input
                type="checkbox"
                checked={form.rememberPassword}
                onChange={(event) => patchForm({ rememberPassword: event.target.checked })}
              />
              <span>{t('siteEditor.rememberPassword')}</span>
            </label>
          </section>
        ) : (
          <section className="editor-grid-two">
            <label className="form-field form-field-full">
              <span>{t('siteEditor.keyPath')}</span>
              <input value={form.keyPath} onChange={(event) => patchForm({ keyPath: event.target.value })} />
            </label>
            <label className="form-field form-field-full">
              <span>{t('siteEditor.keyPassphrase')}</span>
              <input
                type="password"
                value={form.keyPassphrase}
                onChange={(event) => patchForm({ keyPassphrase: event.target.value })}
              />
            </label>
          </section>
        )}

        <details className="advanced-card">
          <summary>{t('siteEditor.advanced')}</summary>
          <div className="editor-grid-two advanced-grid">
            <label className="form-field form-field-full">
              <span>{t('siteEditor.proxyJump')}</span>
              <input value={form.proxyJump} onChange={(event) => patchForm({ proxyJump: event.target.value })} />
            </label>
            <label className="form-field form-field-full">
              <span>{t('siteEditor.sshConfigPath')}</span>
              <input
                value={form.sshConfigPath}
                onChange={(event) => patchForm({ sshConfigPath: event.target.value })}
              />
            </label>
            <label className="form-field form-field-full">
              <span>{t('siteEditor.sshOptions')}</span>
              <textarea
                rows={4}
                value={form.sshOptionsText}
                onChange={(event) => patchForm({ sshOptionsText: event.target.value })}
                placeholder={t('siteEditor.sshOptionsPlaceholder')}
              />
            </label>
          </div>
        </details>
      </form>
    </Modal>
  );
}
