import {
  Activity,
  Bell,
  BellRing,
  ChevronDown,
  CircleDot,
  Clock3,
  Gauge,
  LayoutDashboard,
  Menu,
  Radio,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  Target,
  TrendingUp,
  Trophy,
  Users,
  X,
  Zap,
} from 'lucide-react'
import { useMemo, useState } from 'react'

type Match = {
  id: number
  minute: string
  status: 'LIVE' | 'PRE' | 'FT'
  league: string
  country: string
  home: string
  away: string
  score: string
  form: number[]
  probabilities: [number, number, number]
  xg: string
  signal: string
  edge: number
}

const matches: Match[] = [
  { id: 1, minute: "67'", status: 'LIVE', league: 'Premier League', country: 'ING', home: 'Arsenal', away: 'Liverpool', score: '2 — 1', form: [22, 38, 31, 52, 47, 66, 58, 79], probabilities: [62, 23, 15], xg: '1.84 · 0.96', signal: 'LOCAL +0.5', edge: 8.4 },
  { id: 2, minute: "31'", status: 'LIVE', league: 'LaLiga', country: 'ESP', home: 'Real Madrid', away: 'Real Sociedad', score: '1 — 0', form: [18, 26, 34, 29, 47, 51, 67, 62], probabilities: [71, 19, 10], xg: '1.27 · 0.41', signal: 'OVER 2.5', edge: 6.7 },
  { id: 3, minute: '20:00', status: 'PRE', league: 'Champions League', country: 'EUR', home: 'Inter', away: 'Bayern München', score: '—', form: [55, 41, 46, 39, 48, 43, 35, 44], probabilities: [36, 29, 35], xg: '1.43 · 1.39', signal: 'SIN VENTAJA', edge: 1.2 },
  { id: 4, minute: '21:15', status: 'PRE', league: 'Primera A', country: 'COL', home: 'Atlético Nacional', away: 'Millonarios', score: '—', form: [17, 28, 24, 37, 32, 48, 44, 57], probabilities: [48, 31, 21], xg: '1.51 · 0.92', signal: 'LOCAL DNB', edge: 5.1 },
  { id: 5, minute: 'FT', status: 'FT', league: 'Serie A', country: 'ITA', home: 'AC Milan', away: 'Atalanta', score: '2 — 2', form: [62, 47, 52, 41, 44, 35, 42, 38], probabilities: [34, 37, 29], xg: '1.68 · 1.74', signal: 'CERRADO', edge: 0 },
]

const miniBars = [48, 58, 53, 68, 62, 76, 71, 84, 79, 91, 86, 96]
const nav = [
  ['Centro de mando', LayoutDashboard],
  ['Partidos', Activity],
  ['Mercados IA', Sparkles],
  ['Equipos', Users],
  ['Alertas', Bell],
] as const

function Sparkline({ values, positive = true }: { values: number[]; positive?: boolean }) {
  const points = values.map((value, index) => `${index * (100 / (values.length - 1))},${40 - value * 0.38}`).join(' ')
  return <svg viewBox="0 0 100 42" className="h-9 w-24 overflow-visible" role="img" aria-label="Tendencia"><polyline fill="none" stroke={positive ? '#2dd4bf' : '#fb7185'} strokeWidth="2" vectorEffect="non-scaling-stroke" points={points} /><circle cx="100" cy={40 - values.at(-1)! * 0.38} r="2.5" fill={positive ? '#2dd4bf' : '#fb7185'} /></svg>
}

function Probability({ value, tone }: { value: number; tone: string }) {
  return <div className="min-w-14"><div className="mb-1 flex justify-between font-mono text-[10px]"><span className="text-slate-500">{tone}</span><span className="text-slate-200">{value}%</span></div><div className="h-1 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${tone === '1' ? 'bg-cyan-400' : tone === 'X' ? 'bg-violet-400' : 'bg-rose-400'}`} style={{ width: `${value}%` }} /></div></div>
}

export function DemoPage() {
  const [activeNav, setActiveNav] = useState('Centro de mando')
  const [league, setLeague] = useState('Todas')
  const [timeFilter, setTimeFilter] = useState('En vivo')
  const [selected, setSelected] = useState<Match>(matches[0])
  const [watching, setWatching] = useState<number[]>([1, 4])
  const [confidence, setConfidence] = useState(72)
  const [alert, setAlert] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)
  const [toast, setToast] = useState('')

  const filtered = useMemo(() => {
    let result = league === 'Todas' ? matches : matches.filter((match) => match.league === league)
    if (timeFilter === 'En vivo') result = result.filter((match) => match.status === 'LIVE' || match.status === 'PRE')
    if (timeFilter === 'Próximos') result = result.filter((match) => match.status === 'PRE')
    return result
  }, [league, timeFilter])

  function simulate(message: string) {
    setToast(message)
    globalThis.setTimeout(() => setToast(''), 2600)
  }

  function toggleWatch(id: number) {
    setWatching((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  return <div className="min-h-screen bg-[#05080d] text-slate-200">
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 opacity-50 [background-image:radial-gradient(circle_at_75%_0%,rgba(8,145,178,.12),transparent_30%),linear-gradient(rgba(15,23,42,.15)_1px,transparent_1px),linear-gradient(90deg,rgba(15,23,42,.15)_1px,transparent_1px)] [background-size:auto,40px_40px,40px_40px]" />
    <aside className={`fixed inset-y-0 left-0 z-50 w-64 border-r border-white/5 bg-[#080c13]/95 p-4 backdrop-blur-xl transition-transform lg:translate-x-0 ${mobileMenu ? 'translate-x-0' : '-translate-x-full'}`}>
      <div className="flex h-12 items-center justify-between">
        <div className="flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-300 to-cyan-500 font-black text-slate-950 shadow-[0_0_28px_rgba(34,211,238,.2)]">F</div><div><p className="font-bold tracking-[.18em] text-white">FAIS</p><p className="text-[9px] uppercase tracking-[.26em] text-cyan-400">Sports terminal</p></div></div>
        <button aria-label="Cerrar menú" onClick={() => setMobileMenu(false)} className="text-slate-500 lg:hidden"><X size={19} /></button>
      </div>
      <div className="mt-7 rounded-lg border border-cyan-400/15 bg-cyan-400/[.04] p-3"><div className="flex items-center justify-between"><span className="text-[10px] uppercase tracking-widest text-slate-500">Workspace</span><ChevronDown size={13} className="text-slate-600" /></div><p className="mt-1 text-xs font-medium text-slate-200">Football Intelligence</p></div>
      <nav aria-label="Navegación demo" className="mt-6 space-y-1">{nav.map(([label, Icon]) => <button key={label} onClick={() => { setActiveNav(label); setMobileMenu(false); simulate(`${label}: vista de demostración`) }} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs transition ${activeNav === label ? 'border border-cyan-400/15 bg-cyan-400/10 text-cyan-200' : 'border border-transparent text-slate-500 hover:bg-white/[.03] hover:text-slate-300'}`}><Icon size={16} />{label}{label === 'Alertas' && <span className="ml-auto rounded-full bg-rose-400/15 px-1.5 py-0.5 font-mono text-[9px] text-rose-300">3</span>}</button>)}</nav>
      <div className="absolute inset-x-4 bottom-4 rounded-xl border border-slate-800 bg-slate-900/50 p-3"><div className="flex items-center gap-2"><span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" /></span><span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300">Demo conectada</span></div><p className="mt-2 text-[10px] leading-relaxed text-slate-600">Datos simulados · ninguna acción modifica el sistema.</p></div>
    </aside>

    <main className="relative lg:pl-64">
      <header className="sticky top-0 z-40 flex h-16 items-center gap-3 border-b border-white/5 bg-[#070b11]/85 px-4 backdrop-blur-xl sm:px-6">
        <button aria-label="Abrir menú" onClick={() => setMobileMenu(true)} className="rounded-lg border border-slate-800 p-2 text-slate-400 lg:hidden"><Menu size={18} /></button>
        <div className="relative hidden max-w-md flex-1 sm:block"><Search className="absolute left-3 top-2.5 text-slate-600" size={15} /><input aria-label="Buscar equipos y competiciones" onChange={(event) => event.target.value && setToast(`Buscando “${event.target.value}” en la demo`)} placeholder="Buscar equipo, competición o partido…" className="w-full rounded-lg border border-slate-800/80 bg-slate-950/60 py-2 pl-9 pr-3 text-xs text-slate-200 placeholder:text-slate-700" /></div>
        <div className="ml-auto flex items-center gap-2"><span className="hidden items-center gap-1.5 rounded-full border border-emerald-400/15 bg-emerald-400/[.06] px-2.5 py-1 text-[9px] font-medium uppercase tracking-wider text-emerald-300 sm:flex"><Radio size={10} />Live engine</span><button aria-label="Notificaciones, 3 nuevas" onClick={() => simulate('Tienes 3 señales nuevas')} className="relative rounded-lg border border-slate-800 p-2 text-slate-400"><Bell size={16} /><span className="absolute -right-1 -top-1 grid h-4 w-4 place-items-center rounded-full bg-rose-500 text-[8px] font-bold text-white">3</span></button><button onClick={() => simulate('Perfil de demostración')} className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-violet-400 to-cyan-400 text-[10px] font-bold text-slate-950">FS</button></div>
      </header>

      <div className="mx-auto max-w-[1680px] p-4 sm:p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[.22em] text-cyan-400"><CircleDot size={11} />Centro de mando</div><h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">Inteligencia de partido</h1><p className="mt-1 text-xs text-slate-500">19 octubre 2026 · 148 partidos monitorizados</p></div><div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950/50 p-1">{['En vivo', 'Próximos', 'Finalizados'].map((item) => <button key={item} onClick={() => setTimeFilter(item)} className={`rounded-md px-3 py-1.5 text-[10px] font-medium transition ${timeFilter === item ? 'bg-slate-800 text-white shadow' : 'text-slate-500 hover:text-slate-300'}`}>{item}</button>)}</div></div>

        <section aria-label="Métricas principales" className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ['Partidos en vivo', '24', '+6 desde las 18:00', Activity, 'text-cyan-300 bg-cyan-400/10'],
            ['Señales activas', '11', '4 de alta confianza', Zap, 'text-amber-300 bg-amber-400/10'],
            ['Precisión 30D', '68.7%', '+2.4% vs periodo anterior', Target, 'text-emerald-300 bg-emerald-400/10'],
            ['Modelos operativos', '7 / 8', '1 en reentrenamiento', Gauge, 'text-violet-300 bg-violet-400/10'],
          ].map(([label, value, detail, Icon, tone]) => <article key={String(label)} className="group rounded-xl border border-slate-800/80 bg-gradient-to-br from-slate-900/70 to-[#090d14] p-4 transition hover:-translate-y-0.5 hover:border-slate-700"><div className="flex items-start justify-between"><div><p className="text-[10px] uppercase tracking-widest text-slate-500">{label as string}</p><p className="mt-2 font-mono text-2xl font-semibold text-white">{value as string}</p></div><span className={`rounded-lg p-2 ${tone as string}`}><Icon size={16} /></span></div><p className="mt-3 text-[10px] text-slate-600">{detail as string}</p></article>)}
        </section>

        <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="overflow-hidden rounded-xl border border-slate-800/80 bg-[#090d14]/90">
            <div className="flex flex-col gap-3 border-b border-slate-800/70 p-4 sm:flex-row sm:items-center"><div><h2 className="text-sm font-semibold text-white">Mercado de partidos</h2><p className="mt-0.5 text-[10px] text-slate-600">Probabilidad 1X2 y ventaja estimada por el motor</p></div><div className="ml-auto flex gap-2"><label className="sr-only" htmlFor="league">Filtrar liga</label><select id="league" value={league} onChange={(event) => setLeague(event.target.value)} className="rounded-md border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-[10px] text-slate-400"><option>Todas</option><option>Premier League</option><option>LaLiga</option><option>Champions League</option><option>Primera A</option><option>Serie A</option></select><button aria-label="Más filtros" onClick={() => simulate('Panel de filtros avanzados preparado')} className="rounded-md border border-slate-800 p-2 text-slate-500 hover:text-cyan-300"><SlidersHorizontal size={14} /></button></div></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[820px] text-left"><thead><tr className="border-b border-slate-800/70 text-[9px] uppercase tracking-widest text-slate-600"><th className="px-4 py-3 font-medium">Estado / partido</th><th className="px-3 py-3 font-medium">Momentum</th><th className="px-3 py-3 font-medium">Probabilidad modelo</th><th className="px-3 py-3 font-medium">xG</th><th className="px-3 py-3 font-medium">Señal</th><th className="px-4 py-3 text-right font-medium">Edge</th></tr></thead><tbody>{filtered.map((match) => <tr key={match.id} onClick={() => setSelected(match)} className={`cursor-pointer border-b border-slate-800/50 transition hover:bg-cyan-400/[.025] ${selected.id === match.id ? 'bg-cyan-400/[.04]' : ''}`}><td className="px-4 py-3"><div className="flex items-center gap-3"><button aria-label={`${watching.includes(match.id) ? 'Quitar' : 'Añadir'} ${match.home} de seguimiento`} onClick={(event) => { event.stopPropagation(); toggleWatch(match.id) }}><Star size={14} className={watching.includes(match.id) ? 'fill-amber-300 text-amber-300' : 'text-slate-700'} /></button><span className={`w-10 font-mono text-[10px] ${match.status === 'LIVE' ? 'text-emerald-300' : 'text-slate-600'}`}>{match.minute}</span><div><p className="text-xs font-medium text-slate-200">{match.home} <span className="mx-1 font-mono text-white">{match.score}</span> {match.away}</p><p className="mt-1 text-[9px] uppercase tracking-wider text-slate-600">{match.country} · {match.league}</p></div></div></td><td className="px-3"><Sparkline values={match.form} positive={match.edge > 3} /></td><td className="px-3"><div className="flex gap-2">{match.probabilities.map((value, index) => <Probability key={index} value={value} tone={['1', 'X', '2'][index]} />)}</div></td><td className="px-3 font-mono text-[10px] text-slate-400">{match.xg}</td><td className="px-3"><span className={`rounded border px-2 py-1 font-mono text-[9px] ${match.edge > 3 ? 'border-cyan-400/20 bg-cyan-400/[.06] text-cyan-300' : 'border-slate-700 text-slate-600'}`}>{match.signal}</span></td><td className={`px-4 text-right font-mono text-xs ${match.edge > 3 ? 'text-emerald-300' : 'text-slate-600'}`}>{match.edge ? `+${match.edge}%` : '—'}</td></tr>)}</tbody></table>{filtered.length === 0 && <div className="p-10 text-center text-xs text-slate-600">No hay partidos para este filtro.</div>}</div>
          </div>

          <aside className="space-y-4">
            <div className="rounded-xl border border-slate-800/80 bg-gradient-to-b from-slate-900/80 to-[#090d14] p-4"><div className="flex items-start justify-between"><div><p className="text-[9px] uppercase tracking-[.2em] text-cyan-400">Análisis seleccionado</p><h2 className="mt-2 text-sm font-semibold text-white">{selected.home} vs {selected.away}</h2><p className="mt-1 text-[10px] text-slate-600">{selected.league} · Modelo FAIS Ensemble v3.8</p></div><span className="rounded-md border border-emerald-400/20 bg-emerald-400/[.07] px-2 py-1 font-mono text-[9px] text-emerald-300">{selected.status}</span></div>
              <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950/40 p-4"><div className="flex items-end justify-between"><div><p className="text-[9px] uppercase tracking-widest text-slate-600">Confianza ajustada</p><p className="mt-1 font-mono text-3xl font-semibold text-white">{confidence}%</p></div><Sparkline values={miniBars} /></div><input aria-label="Ajustar confianza del escenario" type="range" min="50" max="95" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} className="mt-4 w-full accent-cyan-400" /><div className="mt-1 flex justify-between text-[8px] uppercase text-slate-700"><span>Conservador</span><span>Agresivo</span></div></div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">{selected.probabilities.map((value, index) => <div key={index} className="rounded-lg border border-slate-800 bg-slate-950/30 p-2"><p className="text-[9px] text-slate-600">{['Local', 'Empate', 'Visitante'][index]}</p><p className="mt-1 font-mono text-sm text-slate-200">{value}%</p></div>)}</div>
              <button onClick={() => simulate(`Simulación preparada al ${confidence}% de confianza`)} className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-400 py-2.5 text-xs font-semibold text-slate-950 transition hover:bg-cyan-300"><Sparkles size={14} />Simular escenario</button><button onClick={() => setAlert(!alert)} className={`mt-2 flex w-full items-center justify-center gap-2 rounded-lg border py-2.5 text-xs transition ${alert ? 'border-amber-300/30 bg-amber-300/[.06] text-amber-200' : 'border-slate-800 text-slate-400 hover:text-slate-200'}`}>{alert ? <BellRing size={14} /> : <Bell size={14} />}{alert ? 'Alerta activada' : 'Crear alerta de señal'}</button>
            </div>
            <div className="rounded-xl border border-slate-800/80 bg-[#090d14]/90 p-4"><div className="flex items-center justify-between"><h2 className="text-xs font-semibold text-white">Salud del sistema</h2><ShieldCheck size={15} className="text-emerald-300" /></div><div className="mt-4 space-y-3">{[['Ingesta de datos', '99.98%', 'bg-emerald-400'], ['Motor predictivo', '42 ms', 'bg-cyan-400'], ['Eventos realtime', '12.4k/m', 'bg-violet-400']].map(([label, value, color]) => <div key={label}><div className="mb-1.5 flex justify-between text-[10px]"><span className="text-slate-500">{label}</span><span className="font-mono text-slate-300">{value}</span></div><div className="h-1 rounded bg-slate-800"><div className={`h-1 w-[92%] rounded ${color}`} /></div></div>)}</div></div>
          </aside>
        </section>

        <footer className="mt-4 flex flex-col gap-2 border-t border-slate-900 pt-4 text-[9px] uppercase tracking-widest text-slate-500 sm:flex-row sm:items-center sm:justify-between"><span>FAIS Terminal · Interactive product preview</span><span className="flex items-center gap-4"><span className="flex items-center gap-1"><Clock3 size={10} />Actualizado ahora</span><span className="flex items-center gap-1"><Trophy size={10} />48 ligas</span><span className="flex items-center gap-1"><TrendingUp size={10} />7 modelos</span></span></footer>
      </div>
    </main>
    {toast && <div role="status" className="fixed bottom-5 left-1/2 z-[70] -translate-x-1/2 rounded-lg border border-cyan-400/20 bg-slate-900/95 px-4 py-3 text-xs text-cyan-100 shadow-2xl backdrop-blur">{toast}</div>}
  </div>
}
