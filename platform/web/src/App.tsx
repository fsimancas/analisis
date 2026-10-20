import { Radio } from 'lucide-react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { Sidebar } from './components/sidebar'
import { MobileNav } from './components/mobile-nav'
import { useRealtime } from './hooks/use-realtime'
import { DashboardPage } from './pages/dashboard'
import { IntelligencePage } from './pages/intelligence'
import { MatchPage } from './pages/match'
import { MatchesPage } from './pages/matches'
import { QualityPage } from './pages/quality'
import { TeamPage } from './pages/team'
import { TeamsPage } from './pages/teams'
import { AccountPage } from './pages/account'
import { AdminPage } from './pages/admin'
import { DemoPage } from './pages/demo'
import { AnalystPage } from './pages/analyst'
import { OddsPage } from './pages/odds'
import { RequireRole } from './components/require-role'
import { PlayerPage } from './pages/player'
import { RefereePage } from './pages/referee'

const titles: Record<string, string> = {
  '/': 'Terminal de análisis',
  '/matches': 'Explorador de partidos',
  '/teams': 'Equipos',
  '/intelligence': 'Inteligencia de modelos',
  '/quality': 'Calidad de datos',
  '/account': 'Cuenta y preferencias',
  '/admin': 'Administración de plataforma',
  '/analyst': 'Mesa del analista',
  '/odds': 'Cuotas y valor esperado',
}

const allRoles = ['USER', 'ANALYST', 'ADMIN'] as const
const analystRoles = ['ANALYST', 'ADMIN'] as const

export default function App() {
  const location = useLocation()
  if (location.pathname === '/demo') return <DemoPage />

  return <PlatformShell />
}

function PlatformShell() {
  const realtime = useRealtime()
  const location = useLocation()
  const title = titles[location.pathname] ?? (location.pathname.startsWith('/matches/') ? 'Ficha del partido' : 'Ficha del equipo')

  return (
    <div className="flex min-h-screen bg-[#070a10] text-slate-200">
      <Sidebar />
      <MobileNav />
      <main className="min-w-0 flex-1">
        <header className="flex h-16 items-center justify-between gap-3 border-b border-slate-800/80 bg-[#090d15]/90 px-4 backdrop-blur md:px-5">
          <div className="min-w-0"><p className="truncate text-xs text-slate-500">Workspace / <span className="text-slate-300">Football Intelligence</span></p><h1 className="truncate text-base font-semibold text-slate-100">{title}</h1></div>
          <div className="flex shrink-0 items-center gap-2 md:gap-3"><Radio aria-hidden="true" size={14} className={realtime.connected ? 'text-emerald-400' : 'text-amber-400'} /><span className="hidden font-mono text-[10px] uppercase tracking-wider text-slate-500 sm:inline">{realtime.connected ? 'Realtime online' : 'API mode'}</span><div className="hidden h-7 w-px bg-slate-800 sm:block" /><span className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-300 md:px-3">UTC</span></div>
        </header>
        <div className="mx-auto max-w-[1600px] p-4 pb-20 md:p-6 md:pb-20 lg:pb-6">
          <Routes>
            <Route path="/" element={<RequireRole roles={[...allRoles]}><DashboardPage /></RequireRole>} />
            <Route path="/matches" element={<RequireRole roles={[...allRoles]}><MatchesPage /></RequireRole>} />
            <Route path="/matches/:matchId" element={<RequireRole roles={[...allRoles]}><MatchPage /></RequireRole>} />
            <Route path="/teams" element={<RequireRole roles={[...allRoles]}><TeamsPage /></RequireRole>} />
            <Route path="/teams/:teamId" element={<RequireRole roles={[...allRoles]}><TeamPage /></RequireRole>} />
            <Route path="/players/:playerId" element={<RequireRole roles={[...allRoles]}><PlayerPage /></RequireRole>} />
            <Route path="/referees/:refereeId" element={<RequireRole roles={[...allRoles]}><RefereePage /></RequireRole>} />
            <Route path="/odds" element={<RequireRole roles={[...allRoles]}><OddsPage /></RequireRole>} />
            <Route path="/analyst" element={<RequireRole roles={[...analystRoles]}><AnalystPage /></RequireRole>} />
            <Route path="/intelligence" element={<RequireRole roles={[...analystRoles]}><IntelligencePage /></RequireRole>} />
            <Route path="/quality" element={<RequireRole roles={[...analystRoles]}><QualityPage /></RequireRole>} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="/admin" element={<RequireRole roles={['ADMIN']}><AdminPage /></RequireRole>} />
          </Routes>
        </div>
      </main>
    </div>
  )
}
