import { Activity, BrainCircuit, Database, Gauge, Radio, Settings2, ShieldCheck, Users } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const navigation = [
  { label: 'Overview', icon: Gauge, to: '/' },
  { label: 'Partidos', icon: Activity, to: '/matches' },
  { label: 'Equipos', icon: Users, to: '/teams' },
  { label: 'Inteligencia', icon: BrainCircuit, to: '/intelligence' },
  { label: 'Calidad', icon: Database, to: '/quality' },
]

export function Sidebar() {
  return (
    <aside className="hidden w-56 shrink-0 border-r border-slate-800/80 bg-[#080b12] p-3 lg:flex lg:flex-col">
      <div className="flex h-14 items-center gap-3 px-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-cyan-400 text-sm font-black text-slate-950">F</div>
        <div><p className="text-sm font-bold tracking-wide text-slate-100">FAIS</p><p className="text-[9px] uppercase tracking-[0.24em] text-cyan-400">Intelligence</p></div>
      </div>
      <nav aria-label="Navegación principal" className="mt-5 space-y-1">
        {navigation.map(({ label, icon: Icon, to }) => (
          <NavLink key={label} to={to} end={to === '/'} className={({ isActive }) => `flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-xs transition ${isActive ? 'bg-cyan-400/10 text-cyan-300' : 'text-slate-500 hover:bg-slate-900 hover:text-slate-300'}`}>
            <Icon size={16} />{label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto space-y-1 border-t border-slate-800 pt-3">
        <NavLink to="/admin" className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-xs text-slate-500 hover:text-slate-300"><ShieldCheck size={15} />Administración</NavLink>
        <button className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-xs text-slate-500 hover:text-slate-300"><Radio size={15} />Fuentes</button>
        <NavLink to="/account" className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-xs text-slate-500 hover:text-slate-300"><Settings2 size={15} />Cuenta</NavLink>
      </div>
    </aside>
  )
}
