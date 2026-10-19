import { useMutation, useQuery } from '@tanstack/react-query'
import { Activity, Bell, BrainCircuit, CalendarClock, Star } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

const pct = (value: number) => `${(value * 100).toFixed(1)}%`

export function MatchPage() {
  const id = Number(useParams().matchId)
  const match = useQuery({ queryKey: ['match', id], queryFn: () => api.match(id), enabled: Number.isFinite(id) })
  const prediction = useQuery({ queryKey: ['prediction', id], queryFn: () => api.prediction(id), enabled: Number.isFinite(id) })
  const favorite = useMutation({ mutationFn: () => api.favoriteMatch(id) })
  const alert = useMutation({ mutationFn: () => api.addAlert(id, 'KICKOFF') })
  if (match.isLoading) return <p className="text-sm text-slate-500">Cargando partido…</p>
  if (!match.data) return <Card className="p-5 text-rose-300">Partido no disponible.</Card>
  const data = match.data
  const markets = prediction.data?.payload.markets
  return <div className="space-y-4">
    <Card className="p-6"><div className="flex flex-wrap items-center justify-between gap-5"><div><p className="text-xs text-cyan-400">{data.competition}</p><h2 className="mt-3 text-2xl font-semibold text-white">{data.home_team} <span className="text-slate-600">vs</span> {data.away_team}</h2><p className="mt-2 flex items-center gap-2 text-xs text-slate-500"><CalendarClock size={14} />{data.kickoff_utc ?? data.kickoff_date ?? data.kickoff_raw}</p><div className="mt-4 flex gap-2">{window.localStorage.getItem('fais_access_token') ? <><button onClick={() => favorite.mutate()} className="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-xs"><Star size={13} />{favorite.isSuccess ? 'Guardado' : 'Favorito'}</button><button onClick={() => alert.mutate()} className="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-xs"><Bell size={13} />{alert.isSuccess ? 'Alerta activa' : 'Avisar al inicio'}</button></> : <Link to="/account" className="text-xs text-cyan-300">Inicia sesión para guardar y crear alertas</Link>}</div></div><div className="text-right"><span className="rounded border border-slate-700 px-2 py-1 font-mono text-[10px]">{data.status}</span><p className="mt-3 font-mono text-4xl font-bold text-cyan-300">{data.home_score === null ? '— : —' : `${data.home_score} : ${data.away_score}`}</p></div></div></Card>
    {markets ? <div className="grid gap-4 lg:grid-cols-3"><Card className="p-5"><p className="flex items-center gap-2 text-xs text-slate-500"><BrainCircuit size={14} />Probabilidad 1X2</p><div className="mt-5 space-y-3">{Object.entries(markets.one_x_two).map(([key,value]) => <div key={key}><div className="mb-1 flex justify-between text-xs"><span className="uppercase text-slate-400">{key}</span><span className="font-mono text-cyan-300">{pct(value)}</span></div><div className="h-1.5 rounded bg-slate-800"><div className="h-full rounded bg-cyan-400" style={{ width: pct(value) }} /></div></div>)}</div></Card><Card className="p-5"><p className="text-xs text-slate-500">Goles esperados</p><div className="mt-6 flex justify-around font-mono text-3xl text-white"><span>{prediction.data?.payload.expected_goals.home.toFixed(2)}</span><span className="text-slate-700">/</span><span>{prediction.data?.payload.expected_goals.away.toFixed(2)}</span></div></Card><Card className="p-5"><p className="flex items-center gap-2 text-xs text-slate-500"><Activity size={14} />Ambos marcan</p><p className="mt-8 font-mono text-4xl font-semibold text-emerald-300">{pct(markets.btts.yes)}</p></Card></div> : <Card className="p-5 text-sm text-slate-500">Todavía no existe una predicción para este partido. El worker puede generarla cuando haya historia suficiente.</Card>}
  </div>
}
