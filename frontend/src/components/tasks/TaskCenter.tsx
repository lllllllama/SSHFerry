import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

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

export function TaskCenter({ fullPage = false }: TaskCenterProps) {
  const items = useTasksStore((state) => state.items);
  const socketStatus = useTasksStore((state) => state.socketStatus);
  const taskCenterExpanded = useUiStore((state) => state.taskCenterExpanded);
  const setTaskCenterExpanded = useUiStore((state) => state.setTaskCenterExpanded);
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
  const isCollapsed = !fullPage && !taskCenterExpanded;

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

    const mutation =
      action === 'pause'
        ? pauseMutation
        : action === 'resume'
          ? resumeMutation
          : action === 'cancel'
            ? cancelMutation
            : restartMutation;

    const results = await Promise.allSettled(selected.map((task) => mutation.mutateAsync(task.task_id)));
    const successCount = results.filter((result) => result.status === 'fulfilled').length;
    pushToast({
      tone: successCount === results.length ? 'success' : 'warning',
      title: t('taskCenter.toast.actionSubmitted', { action: t(`task.action.${action}`) }),
      message: t('taskCenter.toast.actionAccepted', { successCount, total: results.length }),
    });
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
          {!fullPage ? (
            <button
              type="button"
              className="ghost-button"
              onClick={() => setTaskCenterExpanded(!taskCenterExpanded)}
            >
              {taskCenterExpanded ? t('common.collapse') : t('common.expand')}
            </button>
          ) : null}
          {!fullPage ? (
            <Link className="ghost-button link-button" to="/tasks">
              {t('taskCenter.openPage')}
            </Link>
          ) : null}
        </div>
      </header>
      {!isCollapsed ? (
        <>
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
                  void clearFinishedMutation.mutateAsync().then(() => {
                    pushToast({ tone: 'success', title: t('taskCenter.toast.clearedFinished') });
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
                {sortedItems.map((task) => (
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
                    <td>{formatTaskProgress(task)}</td>
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
                        <button type="button" className="row-action" onClick={() => void pauseMutation.mutateAsync(task.task_id)}>
                          {t('task.action.pause')}
                        </button>
                        <button type="button" className="row-action" onClick={() => void resumeMutation.mutateAsync(task.task_id)}>
                          {t('task.action.resume')}
                        </button>
                        <button type="button" className="row-action" onClick={() => void cancelMutation.mutateAsync(task.task_id)}>
                          {t('task.action.cancel')}
                        </button>
                        <button type="button" className="row-action" onClick={() => void restartMutation.mutateAsync(task.task_id)}>
                          {t('task.action.restart')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}
