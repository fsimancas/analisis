import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

export function RefereePage() {
  const id = Number(useParams().refereeId)
  const referee = useQuery({ queryKey: ['referee', id], queryFn: () => api.referee(id), enabled: Number.isFinite(id) })
  if (referee.isLoading) return <p className="text-sm text-slate-500">Cargando árbitro…</p>
  if (!referee.data) return <Card className="p-5 text-rose-300">Árbitro no disponible.</Card>
  const data = referee.data
  const discipline = data.discipline as Record<string, number> | undefined
  return <Card className="max-w-3xl p-6"><p className="text-xs text-cyan-400">Perfil arbitral</p><h2 className="mt-2 text-2xl font-semibold text-white">{String(data.canonical_name)}</h2><p className="mt-2 text-sm text-slate-500">{String(data.category ?? 'Categoría sin confirmar')} · {String(data.country ?? 'Sin país')}</p><div className="mt-6 grid gap-3 sm:grid-cols-3"><div className="rounded border border-slate-800 p-4"><p className="text-[10px] uppercase text-slate-500">Partidos</p><p className="mt-1 font-mono text-2xl">{String(data.matches ?? 0)}</p></div><div className="rounded border border-slate-800 p-4"><p className="text-[10px] uppercase text-slate-500">Amarillas</p><p className="mt-1 font-mono text-2xl text-amber-300">{discipline?.YELLOW_CARD ?? 0}</p></div><div className="rounded border border-slate-800 p-4"><p className="text-[10px] uppercase text-slate-500">Rojas</p><p className="mt-1 font-mono text-2xl text-rose-300">{discipline?.RED_CARD ?? 0}</p></div></div></Card>
}
