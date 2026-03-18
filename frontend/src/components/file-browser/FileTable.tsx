import { useState } from 'react';

import type { TransferDragPayload } from '../../api/types';
import { getTransferDragMime } from '../../api/ws';
import { formatBytes, formatTimestamp } from '../../utils/format';

interface FileLike {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: number;
}

interface FileTableProps<T extends FileLike> {
  entries: T[];
  selectedPaths: string[];
  currentPath: string;
  emptyMessage: string;
  isLoading?: boolean;
  errorMessage?: string | null;
  stale?: boolean;
  onSelect: (path: string, multi: boolean) => void;
  onActivate: (entry: T) => void;
  dragPayloadFactory?: (entry: T) => TransferDragPayload | null;
  onDropTransfer?: (payload: TransferDragPayload, targetPath: string) => void;
}

function readDragPayload(event: React.DragEvent<HTMLElement>): TransferDragPayload | null {
  const raw = event.dataTransfer.getData(getTransferDragMime());
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as TransferDragPayload;
  } catch {
    return null;
  }
}

export function FileTable<T extends FileLike>(props: FileTableProps<T>) {
  const {
    entries,
    selectedPaths,
    currentPath,
    emptyMessage,
    isLoading,
    errorMessage,
    stale,
    onSelect,
    onActivate,
    dragPayloadFactory,
    onDropTransfer,
  } = props;
  const [hoveredPath, setHoveredPath] = useState<string | null>(null);

  function handleDrop(event: React.DragEvent<HTMLElement>, targetPath: string) {
    if (!onDropTransfer) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    setHoveredPath(null);
    const payload = readDragPayload(event);
    if (!payload) {
      return;
    }
    onDropTransfer(payload, targetPath);
  }

  if (isLoading) {
    return <div className="table-state">正在加载目录...</div>;
  }

  if (errorMessage) {
    return (
      <div className="table-state table-state-error">
        <strong>{stale ? 'Session Stale' : '目录加载失败'}</strong>
        <p>{errorMessage}</p>
      </div>
    );
  }

  return (
    <div
      className={`file-table-shell ${hoveredPath === '__background__' ? 'is-drop-target' : ''}`}
      onDragOver={(event) => {
        if (!onDropTransfer) {
          return;
        }
        event.preventDefault();
        setHoveredPath('__background__');
      }}
      onDragLeave={() => {
        if (hoveredPath === '__background__') {
          setHoveredPath(null);
        }
      }}
      onDrop={(event) => handleDrop(event, currentPath)}
    >
      <table className="file-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>大小</th>
            <th>修改时间</th>
          </tr>
        </thead>
        <tbody>
          {!entries.length ? (
            <tr>
              <td colSpan={3} className="table-empty-row">
                {emptyMessage}
              </td>
            </tr>
          ) : null}
          {entries.map((entry) => {
            const selected = selectedPaths.includes(entry.path);
            const rowDrop = entry.is_dir && onDropTransfer;
            return (
              <tr
                key={entry.path}
                className={[
                  selected ? 'is-selected' : '',
                  hoveredPath === entry.path ? 'is-drop-target' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                draggable={Boolean(dragPayloadFactory)}
                onClick={(event) => onSelect(entry.path, event.ctrlKey || event.metaKey)}
                onDoubleClick={() => onActivate(entry)}
                onDragStart={(event) => {
                  if (!dragPayloadFactory) {
                    return;
                  }
                  const payload = dragPayloadFactory(entry);
                  if (!payload) {
                    event.preventDefault();
                    return;
                  }
                  event.dataTransfer.effectAllowed = 'copy';
                  event.dataTransfer.setData(getTransferDragMime(), JSON.stringify(payload));
                }}
                onDragOver={(event) => {
                  if (!rowDrop) {
                    return;
                  }
                  event.preventDefault();
                  event.stopPropagation();
                  setHoveredPath(entry.path);
                }}
                onDragLeave={() => {
                  if (hoveredPath === entry.path) {
                    setHoveredPath(null);
                  }
                }}
                onDrop={(event) => {
                  if (!rowDrop) {
                    return;
                  }
                  handleDrop(event, entry.path);
                }}
              >
                <td className="name-cell">
                  <span className={`entry-icon ${entry.is_dir ? 'entry-dir' : 'entry-file'}`} />
                  <span>{entry.name}</span>
                </td>
                <td>{entry.is_dir ? '--' : formatBytes(entry.size)}</td>
                <td>{formatTimestamp(entry.mtime)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
