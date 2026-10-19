import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Database, Globe2, Radio, Trophy } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { MatchesTable } from '../components/matches-table'
import { MetricCard } from '../components/metric-card'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

const CoverageChart = lazy(() =>
  import('../components/coverage-chart').then((module) => ({ default: module.CoverageChart })),
)
const number = (value?: number) => new Intl.NumberFormat('es-CO').format(value ?? 0)

export function DashboardPage() {
  const overview = useQuery({ queryKey: ['overview'], queryFn: api.overview })
  const competitions = useQuery({ queryKey: ['competitions'], queryFn: () => api.competitions(50) })
  const matches = useQuery({ queryKey: ['matches', 'dashboard'], queryFn: () => api.matches({ limit: 25 }) })
  const loading = overview.isLoading || competitions.isLoading || matches.isLoading
  const error = overview.error || competitions.error || matches.error
  return <>
    {error && <Card className="mb-4 border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-300">No se pudo conectar con FAIS API: {error.message}</Card>}
    <div className="mb-5 flex items-end justify-between"><div><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">System overview</p><h2 className="mt-1 text-2xl font-semibold tracking-tight text-white">Panorama operativo</h2></div><p className="hidden text-xs text-slate-500 md:block">{loading ? 'Sincronizando…' : 'Datos canónicos · lectura en tiempo real'}</p></div>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="Partidos" value={number(overview.data?.counts.matches)} detail="Histórico + próximos" icon={Trophy} />
      <MetricCard label="Competiciones" value={number(overview.data?.counts.competitions)} detail={`${number(overview.data?.counts.countries)} países`} icon={Globe2} tone="violet" />
      <MetricCard label="Equipos" value={number(overview.data?.counts.teams)} detail="Identidades canónicas" icon={Database} tone="emerald" />
      <MetricCard label="Quality flags" value={number(overview.data?.open_quality_issues)} detail="Pendientes de resolución" icon={AlertTriangle} tone="amber" />
    </section>
    <section className="mt-4 grid gap-4 lg:grid-cols-3">
      <Suspense fallback={<Card className="h-[410px] animate-pulse p-4 lg:col-span-2" />}><CoverageChart competitions={competitions.data ?? []} /></Suspense>
      <Card className="p-4"><div className="flex items-center gap-2"><Radio size={15} className="text-emerald-400" /><h2 className="text-sm font-semibold">Pipeline</h2></div><div className="mt-5 space-y-4">{[['Canonical DB','ONLINE','text-emerald-300'],['Prediction worker','READY','text-cyan-300'],['Redis event bus','OPTIONAL','text-amber-300'],['ClickHouse analytics','DEFERRED','text-slate-400']].map(([name,state,color]) => <div key={name} className="flex items-center justify-between border-b border-slate-800/70 pb-3"><span className="text-xs text-slate-400">{name}</span><span className={`font-mono text-[10px] ${color}`}>{state}</span></div>)}</div></Card>
      <MatchesTable matches={matches.data ?? []} />
    </section>
  </>
}
