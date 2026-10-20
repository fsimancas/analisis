import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Bell, BrainCircuit, CalendarClock, Save, Star, Users } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

const pct = (value: number) => `${(value * 100).toFixed(1)}%`

export function MatchPage() {
  const id = Number(useParams().matchId)
  const match = useQuery({ queryKey: ['match', id], queryFn: () => api.match(id), enabled: Number.isFinite(id) })
  const prediction = useQuery({ queryKey: ['prediction', id], queryFn: () => api.prediction(id), enabled: Number.isFinite(id) })
  const details = useQuery({ queryKey: ['match-details', id], queryFn: () => api.matchDetails(id), enabled: Number.isFinite(id) })
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, retry: false })
  const queryClient = useQueryClient()
  const [homePlayers, setHomePlayers] = useState<number[]>([])
  const [awayPlayers, setAwayPlayers] = useState<number[]>([])
  const homeId = details.data?.match.home_team_id ?? 0
  const awayId = details.data?.match.away_team_id ?? 0
  const homeSquad = useQuery({ queryKey: ['squad', homeId], queryFn: () => api.teamSquad(homeId), enabled: Boolean(homeId) })
  const awaySquad = useQuery({ queryKey: ['squad', awayId], queryFn: () => api.teamSquad(awayId), enabled: Boolean(awayId) })
  const favorite = useMutation({ mutationFn: () => api.favoriteMatch(id) })
  const alert = useMutation({ mutationFn: () => api.addAlert(id, 'KICKOFF') })
  const lineup = useMutation({
    mutationFn: ({ teamId, players }: { teamId: number; players: number[] }) => api.saveLineup(id, {
      team_id: teamId,
      status: 'FINAL',
      formation_code: '4-4-2',
      players: players.map((player_id) => ({ player_id, starter: true })),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['match-details', id] }),
  })
  if (match.isLoading) return <p className="text-sm text-slate-500">Cargando partido…</p>
  if (!match.data) return <Card className="p-5 text-rose-300">Partido no disponible.</Card>
  const data = match.data
  const markets = prediction.data?.payload.markets
  return <div className="space-y-4">
    <Card className="p-6"><div className="flex flex-wrap items-center justify-between gap-5"><div><p className="text-xs text-cyan-400">{data.competition}</p><h2 className="mt-3 text-2xl font-semibold text-white">{data.home_team} <span className="text-slate-600">vs</span> {data.away_team}</h2><p className="mt-2 flex items-center gap-2 text-xs text-slate-500"><CalendarClock size={14} />{data.kickoff_utc ?? data.kickoff_date ?? data.kickoff_raw}</p><div className="mt-4 flex gap-2">{window.localStorage.getItem('fais_access_token') ? <><button onClick={() => favorite.mutate()} className="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-xs"><Star size={13} />{favorite.isSuccess ? 'Guardado' : 'Favorito'}</button><button onClick={() => alert.mutate()} className="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-xs"><Bell size={13} />{alert.isSuccess ? 'Alerta activa' : 'Avisar al inicio'}</button></> : <Link to="/account" className="text-xs text-cyan-300">Inicia sesión para guardar y crear alertas</Link>}</div></div><div className="text-right"><span className="rounded border border-slate-700 px-2 py-1 font-mono text-[10px]">{data.status}</span><p className="mt-3 font-mono text-4xl font-bold text-cyan-300">{data.home_score === null ? '— : —' : `${data.home_score} : ${data.away_score}`}</p></div></div></Card>
    {markets ? <div className="grid gap-4 lg:grid-cols-3"><Card className="p-5"><p className="flex items-center gap-2 text-xs text-slate-500"><BrainCircuit size={14} />Probabilidad 1X2</p><div className="mt-5 space-y-3">{Object.entries(markets.one_x_two).map(([key,value]) => <div key={key}><div className="mb-1 flex justify-between text-xs"><span className="uppercase text-slate-400">{key}</span><span className="font-mono text-cyan-300">{pct(value)}</span></div><div className="h-1.5 rounded bg-slate-800"><div className="h-full rounded bg-cyan-400" style={{ width: pct(value) }} /></div></div>)}</div></Card><Card className="p-5"><p className="text-xs text-slate-500">Goles esperados</p><div className="mt-6 flex justify-around font-mono text-3xl text-white"><span>{prediction.data?.payload.expected_goals.home.toFixed(2)}</span><span className="text-slate-700">/</span><span>{prediction.data?.payload.expected_goals.away.toFixed(2)}</span></div></Card><Card className="p-5"><p className="flex items-center gap-2 text-xs text-slate-500"><Activity size={14} />Ambos marcan</p><p className="mt-8 font-mono text-4xl font-semibold text-emerald-300">{pct(markets.btts.yes)}</p></Card></div> : <Card className="p-5 text-sm text-slate-500">Todavía no existe una predicción para este partido. El worker puede generarla cuando haya historia suficiente.</Card>}
    <div className="grid gap-4 lg:grid-cols-2"><TeamPanel name={data.home_team} squad={homeSquad.data ?? []} selected={homePlayers} setSelected={setHomePlayers} canEdit={me.data?.role === 'ANALYST' || me.data?.role === 'ADMIN'} onSave={() => lineup.mutate({ teamId: homeId, players: homePlayers })} /><TeamPanel name={data.away_team} squad={awaySquad.data ?? []} selected={awayPlayers} setSelected={setAwayPlayers} canEdit={me.data?.role === 'ANALYST' || me.data?.role === 'ADMIN'} onSave={() => lineup.mutate({ teamId: awayId, players: awayPlayers })} /></div>
    <div className="grid gap-4 lg:grid-cols-2"><Card className="p-5"><h3 className="text-sm font-semibold">Árbitros</h3><div className="mt-3 space-y-2">{details.data?.referees.map((referee) => <Link key={`${referee.id}-${referee.role}`} to={`/referees/${referee.id}`} className="flex justify-between rounded border border-slate-800 p-3 text-xs hover:border-cyan-400/30"><span>{referee.name}</span><span className="text-slate-500">{referee.role}</span></Link>)}</div></Card><Card className="p-5"><h3 className="text-sm font-semibold">Eventos y estadísticas</h3><div className="mt-3 max-h-64 space-y-2 overflow-auto">{details.data?.events.map((event) => <div key={String(event.id)} className="flex justify-between border-b border-slate-800 py-2 text-xs"><span>{String(event.event_type)} · {String(event.player ?? event.team ?? '')}</span><span className="font-mono text-cyan-300">{String(event.minute ?? '—')}'</span></div>)}{details.data?.team_statistics.map((stat) => <div key={String(stat.id)} className="flex justify-between border-b border-slate-800 py-2 text-xs"><span>{String(stat.team)} · {String(stat.stat_key)}</span><span>{String(stat.raw_value ?? stat.stat_value ?? '—')}</span></div>)}</div></Card></div>
  </div>
}

function TeamPanel({ name, squad, selected, setSelected, canEdit, onSave }: { name: string; squad: Array<Record<string, unknown>>; selected: number[]; setSelected: (value: number[]) => void; canEdit: boolean; onSave: () => void }) {
  const toggle = (id: number) => setSelected(selected.includes(id) ? selected.filter((item) => item !== id) : selected.length < 11 ? [...selected, id] : selected)
  return <Card className="p-5"><div className="flex items-center justify-between"><h3 className="flex items-center gap-2 text-sm font-semibold"><Users size={15} className="text-cyan-300" />{name}</h3><span className="text-[10px] text-slate-500">{selected.length}/11</span></div><div className="mt-3 grid gap-2 sm:grid-cols-2">{squad.map((item) => <label key={String(item.player_id)} className="flex items-center gap-2 rounded border border-slate-800 p-2 text-xs"><input type="checkbox" disabled={!canEdit} checked={selected.includes(Number(item.player_id))} onChange={() => toggle(Number(item.player_id))} /><Link to={`/players/${item.player_id}`} className="hover:text-cyan-300">{String(item.player)} · {String(item.primary_position ?? '')}</Link></label>)}</div>{canEdit && <button disabled={selected.length !== 11} onClick={onSave} className="mt-4 inline-flex items-center gap-2 rounded-md bg-cyan-400 px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-40"><Save size={14} />Guardar alineación final 4-4-2</button>}</Card>
}
