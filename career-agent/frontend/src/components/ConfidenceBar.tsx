export default function ConfidenceBar({ confidence, reason }: { confidence: number; reason?: string }) {
  const pct = Math.round(confidence * 100)
  const color = confidence >= 0.7 ? 'bg-emerald-500' : confidence >= 0.4 ? 'bg-amber-500' : 'bg-slate-400'
  return (
    <div title={reason} className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500 dark:text-slate-400">{pct}%</span>
    </div>
  )
}
