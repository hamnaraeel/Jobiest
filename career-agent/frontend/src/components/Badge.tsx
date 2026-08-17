const PALETTES: Record<string, string> = {
  slate: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  amber: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  red: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
  blue: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  purple: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
}

export type BadgeColor = keyof typeof PALETTES

interface BadgeProps {
  children: React.ReactNode
  color?: BadgeColor
}

export default function Badge({ children, color = 'slate' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${PALETTES[color]}`}>
      {children}
    </span>
  )
}

const STATUS_COLORS: Record<string, BadgeColor> = {
  discovered: 'slate', analyzed: 'slate', matched: 'blue', shortlisted: 'blue',
  preparing: 'amber', ready_to_apply: 'amber', applied: 'blue',
  not_started: 'slate', submitted: 'blue', under_review: 'amber', recruiter_contact: 'amber',
  interview: 'purple', technical_interview: 'purple', final_interview: 'purple',
  offer: 'green', accepted: 'green',
  rejected: 'red', withdrawn: 'slate', ghosted: 'slate', closed: 'slate', archived: 'slate',
  failed: 'red', abandoned: 'slate', blocked: 'red',
  new: 'blue', viewed: 'slate', dismissed: 'slate', completed: 'green', expired: 'slate',
  pending: 'amber', skipped: 'slate', cancelled: 'slate',
  low: 'slate', medium: 'blue', high: 'amber', critical: 'red',
}

export function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? 'slate'
  return <Badge color={color}>{status.replace(/_/g, ' ')}</Badge>
}
