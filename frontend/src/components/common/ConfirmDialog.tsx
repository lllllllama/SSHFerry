import { useState } from 'react';

import { getErrorMessage } from '../../api/http';
import { useI18n } from '../../i18n';
import { useUiStore } from '../../store/ui';
import { Modal } from './Modal';

export function ConfirmDialog() {
  const confirm = useUiStore((state) => state.confirm);
  const closeConfirm = useUiStore((state) => state.closeConfirm);
  const pushToast = useUiStore((state) => state.pushToast);
  const [submitting, setSubmitting] = useState(false);
  const { t } = useI18n();

  async function handleConfirm() {
    if (!confirm.onConfirm) {
      closeConfirm();
      return;
    }
    setSubmitting(true);
    try {
      await confirm.onConfirm();
      closeConfirm();
    } catch (error) {
      pushToast({
        tone: 'danger',
        title: t('common.operationFailed'),
        message: getErrorMessage(error),
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={confirm.open}
      title={confirm.title}
      onClose={() => {
        if (!submitting) {
          closeConfirm();
        }
      }}
      footer={
        <>
          <button type="button" className="ghost-button" onClick={closeConfirm} disabled={submitting}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className={confirm.destructive ? 'danger-button' : 'primary-button'}
            onClick={() => {
              void handleConfirm();
            }}
            disabled={submitting}
          >
            {submitting ? t('common.processing') : confirm.confirmLabel || t('common.confirm')}
          </button>
        </>
      }
    >
      <p className="confirm-copy">{confirm.description}</p>
    </Modal>
  );
}
