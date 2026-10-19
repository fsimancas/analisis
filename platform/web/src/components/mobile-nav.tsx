import { Activity, BrainCircuit, Gauge, Menu, Users } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const items = [
  { label: 'Inicio', icon: Gauge, to: '/' },
  { label: 'Partidos', icon: Activity, to: '/matches' },
  { label: 'Equipos', icon: Users, to: '/teams' },
  { label: 'Modelos', icon: BrainCircuit, to: '/intelligence' },
  { label: 'Cuenta', icon: Menu, to: '/account' },
]

export function MobileNav() {
  return (
    <nav
      aria-label="Navegación principal móvil"
      className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t border-slate-800 bg-[#080b12]/95 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
    >
      {items.map(({ label, icon: Icon, to }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `flex min-h-14 flex-col items-center justify-center gap-1 text-[10px] ${isActive ? 'text-cyan-300' : 'text-slate-500'}`
          }
        >
          <Icon aria-hidden="true" size={17} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
