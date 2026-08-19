import type { ReactNode } from 'react'

interface CardProps {
  title?: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

export default function Card({ title, subtitle, action, children, className = '' }: CardProps) {
  return (
    <section className={`glass-card rounded-2xl p-5 transition-shadow duration-300 hover:shadow-[0_24px_50px_-15px_rgba(0,0,0,0.55)] ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-slate-50">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}
