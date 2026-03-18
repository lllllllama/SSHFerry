export function basename(path: string): string {
  const normalized = path.replace(/[\\/]+$/, '');
  const match = normalized.match(/[^\\/]+$/);
  return match ? match[0] : normalized;
}

export function joinLocalPath(parent: string, child: string): string {
  if (!parent) {
    return child;
  }
  if (/[\\/]$/.test(parent)) {
    return `${parent}${child}`;
  }
  const separator = parent.includes('\\') ? '\\' : '/';
  return `${parent}${separator}${child}`;
}

export function joinRemotePath(parent: string, child: string): string {
  const normalizedParent = parent.endsWith('/') ? parent.slice(0, -1) : parent;
  if (!normalizedParent) {
    return `/${child.replace(/^\/+/, '')}`;
  }
  return `${normalizedParent}/${child.replace(/^\/+/, '')}`;
}
