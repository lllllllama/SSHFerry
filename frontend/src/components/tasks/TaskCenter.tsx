import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import { getErrorMessage } from '../../api/http';
import { cancelTask, clearFinishedTasks, pauseTask, restartTask, resumeTask } from '../../api/tasks';
import type { TaskItem } from '../../api/types';
import { useI18n } from '../../i18n';
import { useTasksStore } from '../../store/tasks';
import { useUiStore } from '../../store/ui';
import { sortTasks } from '../../utils/format';
import { StatusBadge } from '../common/StatusBadge';

interface TaskCenterProps {
  fullPage?: boolean;
}

function getTaskTone(status: string) {
  if (status === 'done') {
    return 'success' as const;
  }
  if (status === 'failed' || status === 'canceled') {
    return 'danger' as const;
  }
  if (status === 'paused' || status === 'pending') {
    return 'warning' as const;
  }
  if (status === 'running') {
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

function countByStatus(items: TaskItem[]) {
  const summary = {
    total: items.length,
    running: 0,
    pending: 0,
    failed: 0,
    done: 0,
  };

  items.forEach((task) => {
    if (task.status === 'running') {
      summary.running += 1;
    }
    if (task.status === 'pending') {
      summary.pending += 1;
    }
    if (task.status === 'failed') {
      summary.failed += 1;
    }
    if (task.status === 'done') {
      summary.done += 1;
    }
  });

  return summary;
}

function isClientWorkspaceUploadTask(task: TaskItem) {
  return task.src_endpoint_type === 'local' && task.dst_endpoint_type === 'workspace';
}

function clampProgress(value: number) {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

export function TaskCenter({ fullPage = false }: TaskCenterProps) {
  const items = useTasksStore((state) => state.items);
  const socketStatus = useTasksStore((state) => state.socketStatus);
  const cancelClientTask = useTasksStore((state) => state.cancelClientTask);
  const clearClientFinished = useTasksStore((state) => state.clearClientFinished);
  const pushToast = useUiStore((state) => state.pushToast);
  const [checkedIds, setCheckedIds] = useState<string[]>([]);
  const { formatDirection, formatSocketStatus, formatTaskProgress, formatTaskStatus, formatTransferSpeed, t } = useI18n();

  const pauseMutation = useMutation({ mutationFn: pauseTask });
  const resumeMutation = useMutation({ mutationFn: resumeTask });
  const cancelMutation = useMutation({ mutationFn: cancelTask });
  const restartMutation = useMutation({ mutationFn: restartTask });
  const clearFinishedMutation = useMutation({ mutationFn: clearFinishedTasks });

  const sortedItems = sortTasks(items);
  const summary = countByStatus(sortedItems);

  useEffect(() => {
    setCheckedIds((current) => current.filter((taskId) => items.some((task) => task.task_id === taskId)));
  }, [items]);

  const actionableTasks = checkedIds.length
    ? sortedItems.filter((task) => checkedIds.includes(task.task_id))
    : [];

  async function runTaskAction(action: 'pause' | 'resume' | 'cancel' | 'restart') {
    const selected = actionableTasks;
    if (!selected.length) {
      return;
    }

    const clientTasks = selected.filter(isClientWorkspaceUploadTask);
    const backendTasks = selected.filter((task) => !isClientWorkspaceUploadTask(task));
    const backendMutation =
      action === 'pause'
        ? pauseMutation
        : action === 'resume'
          ? resumeMutation
          : action === 'cancel'
            ? cancelMutation
            : restartMutation;

    const localSuccessCount = action === 'cancel'
      ? clientTasks.filter((task) => cancelClientTask(task.task_id)).length
      : 0;
    const backendResults = backendTasks.length
      ? await Promise.allSettled(backendTasks.map((task) => backendMutation.mutateAsync(task.task_id)))
      : [];
    const backendSuccessCount = backendResults.filter((result) => result.status === 'fulfilled').length;
    const total = backendTasks.length + (action === 'cancel' ? clientTasks.length : 0);
    const successCount = backendSuccessCount + localSuccessCount;

    if (!total) {
      return;
    }

    pushToast({
      tone: successCount === total ? 'success' : 'warning',
      title: t('taskCenter.toast.actionSubmitted', { action: t(`task.action.${action}`) }),
      message: t('taskCenter.toast.actionAccepted', { successCount, total }),
    });
  }

  async function runRowAction(action: 'pause' | 'resume' | 'cancel' | 'restart', taskId: string) {
    const mutation =
      action === 'pause'
        ? pauseMutation
        : action === 'resume'
          ? resumeMutation
          : action === 'cancel'
            ? cancelMutation
            : restartMutation;
    try {
      await mutation.mutateAsync(taskId);
    } catch (error) {
      pushToast({
        tone: 'danger',
        title: t('taskCenter.toast.actionFailed', { action: t(`task.action.${action}`) }),
        message: getErrorMessage(error),
      });
    }
  }

  return (
    <section className={`panel-shell task-center ${fullPage ? 'task-center-full' : ''}`}>
      <header className="panel-header">
        <div>
          <h3>{t('taskCenter.title')}</h3>
          <p>
            {t('taskCenter.summary', {
              total: summary.total,
              running: summary.running,
              pending: summary.pending,
              failed: summary.failed,
              done: summary.done,
            })}
          </p>
        </div>
        <div className="panel-actions">
          <StatusBadge tone={getSocketTone(socketStatus)}>{formatSocketStatus(socketStatus)}</StatusBadge>
        </div>
      </header>
      <div className="task-toolbar">
        <label className="task-select-all">
          <input
            type="checkbox"
            checked={Boolean(sortedItems.length) && checkedIds.length === sortedItems.length}
            onChange={(event) => {
              setCheckedIds(event.target.checked ? sortedItems.map((task) => task.task_id) : []);
            }}
          />
          {t('common.selectAll')}
        </label>
        <div className="task-toolbar-actions">
          <button type="button" className="ghost-button" onClick={() => void runTaskAction('pause')}>
            {t('task.action.pause')}
          </button>
          <button type="button" className="ghost-button" onClick={() => void runTaskAction('resume')}>
            {t('task.action.resume')}
          </button>
          <button type="button" className="ghost-button" onClick={() => void runTaskAction('cancel')}>
            {t('task.action.cancel')}
          </button>
          <button type="button" className="ghost-button" onClick={() => void runTaskAction('restart')}>
            {t('task.action.restart')}
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              void clearFinishedMutation
                .mutateAsync()
                .then(() => {
                  clearClientFinished();
                  pushToast({ tone: 'success', title: t('taskCenter.toast.clearedFinished') });
                })
                .catch((error: unknown) => {
                  pushToast({
                    tone: 'danger',
                    title: t('taskCenter.toast.clearFailed'),
                    message: getErrorMessage(error),
                  });
                });
            }}
          >
            {t('taskCenter.clearFinished')}
          </button>
        </div>
      </div>
      <div className="task-table-shell">
        <table className="task-table">
          <thead>
            <tr>
              <th />
              <th>{t('common.id')}</th>
              <th>{t('common.direction')}</th>
              <th>{t('common.engine')}</th>
              <th>{t('common.status')}</th>
              <th>{t('common.progress')}</th>
              <th>{t('common.speed')}</th>
              <th>{t('common.current')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {!sortedItems.length ? (
              <tr>
                <td colSpan={9} className="table-empty-row">
                  {t('taskCenter.empty')}
                </td>
              </tr>
            ) : null}
            {sortedItems.map((task) => {
              const progressPercent = clampProgress(task.progress_percent);
              const clientUploadTask = isClientWorkspaceUploadTask(task);
              return (
                <tr key={task.task_id} className={`task-row status-${task.status}`}>
                  <td>
                    <input
                      type="checkbox"
                      checked={checkedIds.includes(task.task_id)}
                      onChange={(event) => {
                        setCheckedIds((current) =>
                          event.target.checked
                            ? [...current, task.task_id]
                            : current.filter((taskId) => taskId !== task.task_id),
                        );
                      }}
                    />
                  </td>
                  <td className="mono-cell">{task.task_id.slice(0, 8)}</td>
                  <td>{formatDirection(task.src_endpoint_type, task.dst_endpoint_type)}</td>
                  <td>{task.engine.toUpperCase()}</td>
                  <td>
                    <StatusBadge tone={getTaskTone(task.status)}>{formatTaskStatus(task.status)}</StatusBadge>
                  </td>
                  <td>
                    <div className="task-progress-cell">
                      <div className="task-progress-bar" aria-hidden="true">
                        <span className="task-progress-fill" style={{ width: `${progressPercent}%` }} />
                      </div>
                      <div className="task-progress-copy">{formatTaskProgress(task)}</div>
                    </div>
                  </td>
                  <td>{formatTransferSpeed(task.speed)}</td>
                  <td className="task-current-cell">
                    <div>{task.current_file || task.dst_label}</div>
                    {task.error_message ? (
                      <details>
                        <summary>{t('common.viewFailureDetails')}</summary>
                        <p>{task.error_message}</p>
                      </details>
                    ) : null}
                  </td>
                  <td>
                    <div className="inline-actions compact-actions">
                      {clientUploadTask ? (
                        !task.is_finished ? (
                          <button type="button" className="row-action" onClick={() => cancelClientTask(task.task_id)}>
                            {t('task.action.cancel')}
                          </button>
                        ) : null
                      ) : (
                        <>
                          {task.status === 'running' ? (
                            <button type="button" className="row-action" onClick={() => void runRowAction('pause', task.task_id)}>
                              {t('task.action.pause')}
                            </button>
                          ) : null}
                          {task.status === 'paused' ? (
                            <button type="button" className="row-action" onClick={() => void runRowAction('resume', task.task_id)}>
                              {t('task.action.resume')}
                            </button>
                          ) : null}
                          {!task.is_finished ? (
                            <button type="button" className="row-action" onClick={() => void runRowAction('cancel', task.task_id)}>
                              {t('task.action.cancel')}
                            </button>
                          ) : null}
                          {task.status === 'failed' || task.status === 'canceled' ? (
                            <button type="button" className="row-action" onClick={() => void runRowAction('restart', task.task_id)}>
                              {t('task.action.restart')}
                            </button>
                          ) : null}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}