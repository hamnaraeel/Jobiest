import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/discovery', label: 'Discovery', end: false },
  { to: '/recommendations', label: 'Recommendations', end: false },
  { to: '/jobs', label: 'Jobs', end: false },
  { to: '/applications', label: 'Applications', end: false },
]

export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white px-4 py-6 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-8 px-2">
          <h1 className="text-lg font-semibold tracking-tight">Career Agent</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">Job search command center</p>
        </div>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-2 text-xs text-slate-400 dark:text-slate-500">
          Local-first · no data leaves your machine
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
