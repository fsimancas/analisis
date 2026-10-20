import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

export function PlayerPage() {
  const id = Number(useParams().playerId)
  const player = useQuery({ queryKey: ['player', id], queryFn: () => api.player(id), enabled: Number.isFinite(id) })
  if (player.isLoading) return <p className="text-sm text-slate-500">Cargando jugador…</p>
  if (!player.data) return <Card className="p-5 text-rose-300">Jugador no disponible.</Card>
  const data = player.data
  const stats = Array.isArray(data.statistics) ? data.statistics as Array<Record<string, unknown>> : []
  const squads = Array.isArray(data.squads) ? data.squads as Array<Record<string, unknown>> : []
  return <div className="grid gap-4 lg:grid-cols-2"><Card className="p-6"><p className="text-xs text-cyan-400">Perfil del jugador</p><h2 className="mt-2 text-2xl font-semibold text-white">{String(data.canonical_name)}</h2><p className="mt-2 text-sm text-slate-500">{String(data.primary_position ?? 'Posición sin confirmar')} · {String(data.country ?? 'Sin país')}</p><p className="mt-4 text-xs text-slate-500">Nacimiento: {String(data.date_of_birth ?? '—')}</p><div className="mt-5 space-y-2">{squads.map((squad) => <div key={String(squad.id)} className="rounded border border-slate-800 p-3 text-xs">{String(squad.team)} · #{String(squad.shirt_number ?? '—')}</div>)}</div></Card><Card className="p-6"><h3 className="text-sm font-semibold">Rendimiento agregado</h3><div className="mt-4 space-y-2">{stats.map((stat) => <div key={String(stat.stat_key)} className="flex justify-between border-b border-slate-800 py-2 text-xs"><span>{String(stat.stat_key)}</span><span className="font-mono text-cyan-300">{Number(stat.total ?? 0).toFixed(2)} · avg {Number(stat.average ?? 0).toFixed(2)}</span></div>)}</div></Card></div>
}
