import { useMemo, useRef, useState } from 'react';

import type { TransferDragPayload } from '../../api/types';
import { getTransferDragMime } from '../../api/ws';
import { useI18n } from '../../i18n';
import { formatBytes } from '../../utils/format';

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
  onSelectRange?: (paths: string[]) => void;
  onActivate: (entry: T) => void;
  onDeleteSelection?: () => void;
  getEntrySubtitle?: (entry: T) => string | null;
  highlightQuery?: string;
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

function buildHighlightTerms(query: string | undefined): string[] {
  if (!query) {
    return [];
  }
  return query
    .split(/\s+/)
    .map((term) => term.replace(/[*?[\]]/g, '').trim().toLowerCase())
    .filter((term) => term.length > 0)
    .sort((left, right) => right.length - left.length);
}

function renderHighlightedName(name: string, terms: string[]) {
  if (!terms.length) {
    return name;
  }

  const loweredName = name.toLowerCase();
  const ranges: Array<[number, number]> = [];
  for (const term of terms) {
    let start = 0;
    while (start < loweredName.length) {
      const index = loweredName.indexOf(term, start);
      if (index < 0) {
        break;
      }
      const end = index + term.length;
      if (!ranges.some(([rangeStart, rangeEnd]) => index < rangeEnd && end > rangeStart)) {
        ranges.push([index, end]);
      }
      start = end;
    }
  }

  if (!ranges.length) {
    return name;
  }

  ranges.sort(([leftStart], [rightStart]) => leftStart - rightStart);
  const pieces: JSX.Element[] = [];
  let cursor = 0;
  ranges.forEach(([start, end], index) => {
    if (cursor < start) {
      pieces.push(<span key={`text-${index}`}>{name.slice(cursor, start)}</span>);
    }
    pieces.push(
      <mark key={`mark-${index}`} className="entry-name-match">
        {name.slice(start, end)}
      </mark>,
    );
    cursor = end;
  });
  if (cursor < name.length) {
    pieces.push(<span key="text-tail">{name.slice(cursor)}</span>);
  }
  return pieces;
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
    onSelectRange,
    onActivate,
    onDeleteSelection,
    getEntrySubtitle,
    highlightQuery,
    dragPayloadFactory,
    onDropTransfer,
  } = props;
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [hoveredPath, setHoveredPath] = useState<string | null>(null);
  const [selectionAnchorPath, setSelectionAnchorPath] = useState<string | null>(null);
  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths]);
  const highlightTerms = useMemo(() => buildHighlightTerms(highlightQuery), [highlightQuery]);
  const { formatDateTime, t } = useI18n();

  function handleRowClick(entry: T, event: React.MouseEvent<HTMLTableRowElement>) {
    shellRef.current?.focus();
    if (event.shiftKey && selectionAnchorPath && onSelectRange) {
      const anchorIndex = entries.findIndex((item) => item.path === selectionAnchorPath);
      const targetIndex = entries.findIndex((item) => item.path === entry.path);
      if (anchorIndex >= 0 && targetIndex >= 0) {
        const [start, end] = [anchorIndex, targetIndex].sort((left, right) => left - right);
        onSelectRange(entries.slice(start, end + 1).map((item) => item.path));
        return;
      }
    }

    setSelectionAnchorPath(entry.path);
    onSelect(entry.path, event.ctrlKey || event.metaKey);
  }

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
    return <div className="table-state">{t('common.loadingDirectory')}</div>;
  }

  if (errorMessage) {
    return (
      <div className="table-state table-state-error">
        <strong>{stale ? t('common.stale') : t('common.directoryLoadFailed')}</strong>
        <p>{errorMessage}</p>
      </div>
    );
  }

  return (
    <div
      ref={shellRef}
      className={`file-table-shell ${hoveredPath === '__background__' ? 'is-drop-target' : ''}`}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Delete' && selectedPaths.length && onDeleteSelection) {
          event.preventDefault();
          onDeleteSelection();
        }
      }}
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
        <colgroup>
          <col />
          <col className="file-table-size-col" />
          <col className="file-table-modified-col" />
        </colgroup>
        <thead>
          <tr>
            <th>{t('common.name')}</th>
            <th className="file-table-size-cell">{t('common.size')}</th>
            <th className="file-table-modified-cell">{t('common.modified')}</th>
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
            const selected = selectedSet.has(entry.path);
            const rowDrop = entry.is_dir && onDropTransfer;
            const subtitle = getEntrySubtitle?.(entry);
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
                onClick={(event) => handleRowClick(entry, event)}
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
                <td className="name-cell" title={entry.path}>
                  <span className={`entry-icon ${entry.is_dir ? 'entry-dir' : 'entry-file'}`} />
                  <span className="entry-copy">
                    <span className={`entry-name ${entry.is_dir ? 'entry-name-dir' : ''}`}>
                      {renderHighlightedName(entry.name, highlightTerms)}
                    </span>
                    {subtitle ? <span className="entry-subtitle">{subtitle}</span> : null}
                  </span>
                </td>
                <td className="file-table-size-cell">{entry.is_dir ? '--' : formatBytes(entry.size)}</td>
                <td className="file-table-modified-cell">{formatDateTime(entry.mtime)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
