import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard', end: true, icon: '◈' },
  { to: '/profile', label: 'Profile', end: false, icon: '◐' },
  { to: '/discovery', label: 'Discovery', end: false, icon: '✦' },
  { to: '/recommendations', label: 'Recommendations', end: false, icon: '◆' },
  { to: '/jobs', label: 'Jobs', end: false, icon: '▣' },
  { to: '/applications', label: 'Applications', end: false, icon: '▤' },
]

export default function App() {
  return (
    <div className="flex min-h-screen text-slate-100">
      <aside className="glass-panel sticky top-4 m-4 flex h-[calc(100vh-2rem)] w-64 shrink-0 flex-col rounded-2xl px-4 py-6">
        <div className="mb-8 flex items-center gap-3 px-2">
          <div className="gradient-accent glow-accent flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-base font-bold text-white">
            J
          </div>
          <div>
            <h1 className="gradient-text text-base font-semibold tracking-tight">Jobiest</h1>
            <p className="text-[11px] text-slate-400">Job search command center</p>
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `group flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'gradient-accent glow-accent text-white'
                    : 'text-slate-300 hover:bg-white/[0.06] hover:text-white'
                }`
              }
            >
              <span className="text-sm opacity-80">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex items-center gap-2 rounded-xl bg-white/[0.04] px-3 py-2.5 text-[11px] text-slate-400">
          <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-emerald-400" />
          Local-first · no data leaves your machine
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
