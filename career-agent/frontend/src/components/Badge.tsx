const PALETTES: Record<string, string> = {
  slate: 'bg-white/[0.06] text-slate-300 border border-white/10',
  green: 'bg-emerald-500/15 text-emerald-300 border border-emerald-400/20',
  amber: 'bg-amber-500/15 text-amber-300 border border-amber-400/20',
  red: 'bg-rose-500/15 text-rose-300 border border-rose-400/20',
  blue: 'bg-indigo-500/15 text-indigo-300 border border-indigo-400/20',
  purple: 'bg-fuchsia-500/15 text-fuchsia-300 border border-fuchsia-400/20',
}

export type BadgeColor = keyof typeof PALETTES

interface BadgeProps {
  children: React.ReactNode
  color?: BadgeColor
}

export default function Badge({ children, color = 'slate' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium backdrop-blur-sm ${PALETTES[color]}`}>
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
