import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

const VARIANTS: Record<Variant, string> = {
  primary: 'gradient-accent text-white shadow-[0_8px_24px_-6px_rgba(139,92,246,0.55)] hover:brightness-110 hover:shadow-[0_10px_30px_-6px_rgba(139,92,246,0.7)] disabled:opacity-40 disabled:hover:brightness-100',
  secondary: 'bg-white/[0.06] text-slate-200 border border-white/10 hover:bg-white/[0.1] hover:border-white/20',
  danger: 'bg-rose-500/15 text-rose-300 border border-rose-400/20 hover:bg-rose-500/25',
  ghost: 'text-slate-300 hover:bg-white/[0.06] hover:text-white',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

export default function Button({ variant = 'secondary', className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}
