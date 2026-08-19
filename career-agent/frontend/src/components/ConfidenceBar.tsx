export default function ConfidenceBar({ confidence, reason }: { confidence: number; reason?: string }) {
  const pct = Math.round(confidence * 100)
  const color =
    confidence >= 0.7
      ? 'bg-gradient-to-r from-emerald-400 to-teal-300 shadow-[0_0_10px_rgba(52,211,153,0.6)]'
      : confidence >= 0.4
        ? 'bg-gradient-to-r from-amber-400 to-orange-300 shadow-[0_0_10px_rgba(251,191,36,0.5)]'
        : 'bg-slate-500'
  return (
    <div title={reason} className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-white/[0.08]">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400">{pct}%</span>
    </div>
  )
}
