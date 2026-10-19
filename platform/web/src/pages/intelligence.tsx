import { useQuery } from '@tanstack/react-query'
import { BrainCircuit, CheckCircle2 } from 'lucide-react'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

const percent = (value?: number) => value === undefined ? '—' : `${(value * 100).toFixed(2)}%`

export function IntelligencePage() {
  const models = useQuery({ queryKey: ['models'], queryFn: api.models })
  const backtests = useQuery({ queryKey: ['backtests'], queryFn: api.backtests })
  return <><div className="mb-5"><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Model registry</p><h2 className="mt-1 text-2xl font-semibold text-white">Inteligencia</h2></div><div className="grid gap-4 lg:grid-cols-3"><Card className="p-5 lg:col-span-1"><div className="flex items-center gap-2 text-sm font-semibold"><BrainCircuit size={16} className="text-cyan-300" />Modelos</div><div className="mt-5 space-y-3">{(models.data ?? []).map((model) => <div key={model.id} className="rounded-md border border-slate-800 p-3"><div className="flex justify-between"><span className="text-sm text-slate-200">{model.name}</span>{model.active && <CheckCircle2 size={15} className="text-emerald-400" />}</div><p className="mt-1 font-mono text-[10px] text-slate-500">{model.version}</p><p className="mt-2 text-xs text-slate-600">{model.algorithm} · {model.feature_version}</p></div>)}</div></Card><Card className="overflow-hidden lg:col-span-2"><div className="border-b border-slate-800 px-4 py-3 text-sm font-semibold">Backtests walk-forward</div><div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="px-4 py-3">Versión</th><th>Partidos</th><th>Accuracy</th><th>Log loss</th><th>ECE</th><th>Estado</th></tr></thead><tbody>{(backtests.data ?? []).map((run) => <tr key={run.id} className="border-t border-slate-800/70"><td className="px-4 py-3 font-mono text-cyan-300">{run.version}</td><td>{run.metrics?.evaluated ?? '—'}</td><td>{percent(run.metrics?.accuracy)}</td><td>{run.metrics?.log_loss?.toFixed(4) ?? '—'}</td><td>{percent(run.metrics?.expected_calibration_error)}</td><td className="text-emerald-300">{run.status}</td></tr>)}</tbody></table></div></Card></div></>
}
