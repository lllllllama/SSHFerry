interface StatusBadgeProps {
  tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
  children: string;
}

export function StatusBadge({ tone, children }: StatusBadgeProps) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}
