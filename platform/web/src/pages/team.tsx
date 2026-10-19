import { useMutation, useQuery } from '@tanstack/react-query'
import { Activity, Goal, Star, TrendingUp, Trophy } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { MatchesTable } from '../components/matches-table'
import { MetricCard } from '../components/metric-card'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

export function TeamPage() {
  const id = Number(useParams().teamId)
  const team = useQuery({ queryKey: ['team', id], queryFn: () => api.team(id), enabled: Number.isFinite(id) })
  const matches = useQuery({ queryKey: ['team-matches', id], queryFn: () => api.matches({ team_id: id, limit: 30 }), enabled: Number.isFinite(id) })
  const favorite = useMutation({ mutationFn: () => api.favoriteTeam(id) })
  if (!team.data) return <p className="text-sm text-slate-500">Cargando equipo…</p>
  const data = team.data
  return <div className="space-y-4"><Card className="p-5"><p className="text-xs text-cyan-400">{data.country}</p><div className="flex items-center justify-between"><h2 className="mt-1 text-2xl font-semibold text-white">{data.name}</h2>{window.localStorage.getItem('fais_access_token') && <button onClick={() => favorite.mutate()} className="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-xs"><Star size={13} />{favorite.isSuccess ? 'Guardado' : 'Seguir equipo'}</button>}</div><div className="mt-4 flex gap-2">{data.form.map((result,index) => <span key={`${result}-${index}`} className={`grid h-7 w-7 place-items-center rounded font-mono text-xs ${result === 'W' ? 'bg-emerald-400/15 text-emerald-300' : result === 'D' ? 'bg-amber-400/15 text-amber-300' : 'bg-rose-400/15 text-rose-300'}`}>{result}</span>)}</div></Card><section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Jugados" value={String(data.played)} detail="Partidos finalizados" icon={Activity} /><MetricCard label="Victorias" value={String(data.wins)} detail={`${data.draws} empates`} icon={Trophy} tone="emerald" /><MetricCard label="Goles" value={String(data.goals_for)} detail={`${data.goals_against} recibidos`} icon={Goal} tone="violet" /><MetricCard label="Win rate" value={data.played ? `${((data.wins/data.played)*100).toFixed(1)}%` : '—'} detail="Histórico disponible" icon={TrendingUp} tone="amber" /></section><MatchesTable matches={matches.data ?? []} /></div>
}
