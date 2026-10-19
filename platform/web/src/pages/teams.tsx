import { useQuery } from '@tanstack/react-query'
import { Search, Shield } from 'lucide-react'
import { useDeferredValue, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

export function TeamsPage() {
  const [search, setSearch] = useState('')
  const deferred = useDeferredValue(search)
  const teams = useQuery({ queryKey: ['teams', deferred], queryFn: () => api.teams(deferred, 100) })
  return <><div className="mb-5"><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Team terminal</p><h2 className="mt-1 text-2xl font-semibold text-white">Equipos</h2></div><label className="mb-4 flex max-w-md items-center gap-2 rounded-md border border-slate-800 bg-slate-950/60 px-3"><Search size={15} className="text-slate-600" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar equipo" className="w-full bg-transparent py-2.5 text-sm outline-none placeholder:text-slate-700" /></label><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{(teams.data ?? []).map((team) => <Link key={team.id} to={`/teams/${team.id}`}><Card className="p-4 transition hover:border-cyan-400/30"><div className="flex items-start gap-3"><div className="rounded-md bg-slate-800 p-2 text-cyan-300"><Shield size={18} /></div><div><h3 className="text-sm font-medium text-slate-200">{team.name}</h3><p className="mt-1 text-xs text-slate-600">{team.country ?? 'Internacional'}</p><p className="mt-3 font-mono text-[10px] text-slate-500">{team.match_count} partidos</p></div></div></Card></Link>)}</div></>
}
