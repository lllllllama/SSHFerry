import { useEffect, useState } from 'react';

import type { SiteResponse } from '../../api/types';
import { Modal } from '../common/Modal';

interface SecretPromptDialogProps {
  open: boolean;
  site: SiteResponse | null;
  title: string;
  submitLabel: string;
  onClose: () => void;
  onSubmit: (payload: { password?: string; keyPassphrase?: string }) => void | Promise<void>;
}

export function SecretPromptDialog({
  open,
  site,
  title,
  submitLabel,
  onClose,
  onSubmit,
}: SecretPromptDialogProps) {
  const [secret, setSecret] = useState('');

  useEffect(() => {
    if (open) {
      setSecret('');
    }
  }, [open, site?.name]);

  const isPassword = site?.auth_method === 'password';

  return (
    <Modal
      open={open}
      title={title}
      description={site ? `${site.username}@${site.host}:${site.port}` : ''}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="ghost-button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              void onSubmit(isPassword ? { password: secret } : { keyPassphrase: secret });
            }}
          >
            {submitLabel}
          </button>
        </>
      }
    >
      <label className="form-field">
        <span>{isPassword ? '运行时密码' : '私钥口令'}</span>
        <input
          type="password"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          placeholder={isPassword ? '输入本次连接使用的密码' : '如无私钥口令可留空'}
        />
      </label>
    </Modal>
  );
}
