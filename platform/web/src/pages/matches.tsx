import { useQuery } from '@tanstack/react-query'
import { CalendarDays, ChevronRight } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

const statuses = ['', 'SCHEDULED', 'FINISHED', 'POSTPONED']

export function MatchesPage() {
  const [params] = useSearchParams()
  const status = params.get('status') ?? ''
  const matches = useQuery({ queryKey: ['matches', status], queryFn: () => api.matches({ limit: 100, status: status || undefined }) })
  return <>
    <div className="mb-5"><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Match explorer</p><h2 className="mt-1 text-2xl font-semibold text-white">Partidos</h2></div>
    <div className="mb-4 flex flex-wrap gap-2">{statuses.map((value) => <Link key={value || 'all'} to={value ? `/matches?status=${value}` : '/matches'} className={`rounded-md border px-3 py-2 text-xs ${status === value ? 'border-cyan-400/40 bg-cyan-400/10 text-cyan-300' : 'border-slate-800 text-slate-500'}`}>{value || 'TODOS'}</Link>)}</div>
    <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[800px] text-left text-xs"><thead className="bg-slate-950/50 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3">Fecha</th><th>Competición</th><th>Partido</th><th>Estado</th><th>Marcador</th><th /></tr></thead><tbody>{(matches.data ?? []).map((match) => <tr key={match.id} className="border-t border-slate-800/70 hover:bg-cyan-400/[0.025]"><td className="px-4 py-3 font-mono text-slate-500"><span className="inline-flex items-center gap-2"><CalendarDays size={13} />{match.kickoff_date ?? 'Sin fecha'}</span></td><td className="text-slate-500">{match.competition}</td><td className="font-medium text-slate-200">{match.home_team} <span className="text-slate-600">vs</span> {match.away_team}</td><td><span className="rounded border border-slate-700 px-2 py-1 font-mono text-[10px]">{match.status}</span></td><td className="font-mono text-cyan-300">{match.home_score === null ? '—' : `${match.home_score} : ${match.away_score}`}</td><td><Link to={`/matches/${match.id}`} aria-label="Abrir partido"><ChevronRight size={15} /></Link></td></tr>)}</tbody></table></div></Card>
  </>
}
