import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, Play, Save, TestTube2 } from 'lucide-react'
import { FormEvent, useMemo, useState } from 'react'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

const percent = (value: number) => `${(value * 100).toFixed(2)}%`

export function AnalystPage() {
  const queryClient = useQueryClient()
  const matches = useQuery({ queryKey: ['analyst-matches'], queryFn: api.analystMatches })
  const workbooks = useQuery({ queryKey: ['workbooks'], queryFn: api.workbooks })
  const [matchId, setMatchId] = useState(0)
  const [iterations, setIterations] = useState(50000)
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const selected = useMemo(() => matches.data?.find((item) => item.id === matchId), [matches.data, matchId])
  const runs = useQuery({
    queryKey: ['analysis-runs', matchId],
    queryFn: () => api.analysisRuns(matchId || undefined),
  })
  const prediction = useMutation({ mutationFn: () => api.analystPredict(matchId) })
  const simulation = useMutation({
    mutationFn: () => api.monteCarlo(matchId, iterations),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['analysis-runs'] }),
  })
  const backtest = useMutation({ mutationFn: api.analystBacktest })
  const workbook = useMutation({
    mutationFn: () => api.saveWorkbook({
      match_id: matchId || undefined,
      title,
      notes,
      payload: simulation.data?.result ? { simulation: simulation.data.result } : {},
    }),
    onSuccess: () => {
      setTitle('')
      setNotes('')
      queryClient.invalidateQueries({ queryKey: ['workbooks'] })
    },
  })

  function save(event: FormEvent) {
    event.preventDefault()
    workbook.mutate()
  }

  const result = simulation.data?.result
  return <>
    <div className="mb-5"><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Analyst workspace</p><h2 className="mt-1 text-2xl font-semibold text-white">Mesa de análisis</h2><p className="mt-2 text-sm text-slate-500">Predicción, Monte Carlo reproducible, backtests y cuadernos en una sola vista.</p></div>
    <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
      <div className="space-y-4">
        <Card className="p-5"><label className="text-xs text-slate-400">Partido</label><select aria-label="Partido" value={matchId} onChange={(event) => setMatchId(Number(event.target.value))} className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2.5 text-sm"><option value={0}>Selecciona un partido</option>{matches.data?.map((match) => <option key={match.id} value={match.id}>{match.kickoff_date ?? 'Sin fecha'} · {match.home_team} vs {match.away_team}</option>)}</select><div className="mt-4 flex flex-wrap gap-2"><button disabled={!matchId || prediction.isPending} onClick={() => prediction.mutate()} className="inline-flex items-center gap-2 rounded-md bg-cyan-400 px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-40"><BrainCircuit size={14} />Calcular predicción</button><input aria-label="Iteraciones" type="number" min={1000} max={100000} step={1000} value={iterations} onChange={(event) => setIterations(Number(event.target.value))} className="w-32 rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-xs" /><button disabled={!matchId || simulation.isPending} onClick={() => simulation.mutate()} className="inline-flex items-center gap-2 rounded-md border border-cyan-400/40 px-3 py-2 text-xs text-cyan-300 disabled:opacity-40"><Play size={14} />Monte Carlo</button><button onClick={() => backtest.mutate()} className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-xs"><TestTube2 size={14} />Backtest</button></div>{prediction.data && <p className="mt-3 text-xs text-emerald-300">Predicción en cola: {prediction.data.id}</p>}</Card>
        {result && <Card className="p-5"><h3 className="text-sm font-semibold">Resultado · {selected?.home_team} vs {selected?.away_team}</h3><div className="mt-4 grid gap-3 sm:grid-cols-3">{Object.entries(result.one_x_two).map(([key, value]) => <div key={key} className="rounded-md border border-slate-800 p-3"><p className="text-[10px] uppercase text-slate-500">{key}</p><p className="mt-1 font-mono text-xl text-cyan-300">{percent(value)}</p></div>)}</div><div className="mt-4 grid gap-2 sm:grid-cols-2">{Object.entries(result.markets).map(([key, value]) => <div key={key} className="flex justify-between border-b border-slate-800 py-2 text-xs"><span className="text-slate-500">{key}</span><span>{percent(value)}</span></div>)}</div><p className="mt-4 text-[10px] text-slate-600">{result.iterations.toLocaleString()} iteraciones · semilla {result.seed} · {result.version}</p></Card>}
        <Card className="overflow-hidden"><div className="border-b border-slate-800 px-4 py-3 text-sm font-semibold">Ejecuciones recientes</div><div className="divide-y divide-slate-800">{runs.data?.slice(0, 12).map((run) => <div key={run.id} className="flex items-center justify-between px-4 py-3 text-xs"><span>{run.analysis_type} · partido #{run.match_id}</span><span className="font-mono text-emerald-300">{run.status}</span></div>)}</div></Card>
      </div>
      <div className="space-y-4"><Card className="p-5"><h3 className="text-sm font-semibold">Guardar cuaderno</h3><form onSubmit={save} className="mt-4 space-y-3"><input required minLength={2} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Título del análisis" className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm" /><textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Hipótesis y observaciones" rows={6} className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm" /><button disabled={workbook.isPending} className="inline-flex items-center gap-2 rounded-md bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-950"><Save size={14} />Guardar</button></form></Card><Card className="p-5"><h3 className="text-sm font-semibold">Mis cuadernos</h3><div className="mt-3 space-y-2">{workbooks.data?.map((item) => <div key={item.id} className="rounded-md border border-slate-800 p-3"><p className="text-xs text-slate-200">{item.title}</p><p className="mt-1 line-clamp-2 text-xs text-slate-500">{item.notes || 'Sin notas'}</p></div>)}</div></Card></div>
    </div>
  </>
}
