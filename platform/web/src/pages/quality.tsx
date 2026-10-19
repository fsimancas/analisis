import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

export function QualityPage() {
  const issues = useQuery({ queryKey: ['quality'], queryFn: () => api.qualityIssues(200) })
  return <><div className="mb-5"><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Data observability</p><h2 className="mt-1 text-2xl font-semibold text-white">Calidad de datos</h2><p className="mt-2 text-sm text-slate-500">Las fechas sin hora son utilizables cronológicamente, pero se mantienen marcadas para enriquecimiento.</p></div><Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-xs"><thead className="bg-slate-950/50 text-[10px] uppercase text-slate-500"><tr><th className="px-4 py-3">Severidad</th><th>Código</th><th>Entidad</th><th>Valor original</th><th>Estado</th></tr></thead><tbody>{(issues.data ?? []).map((issue) => <tr key={issue.id} className="border-t border-slate-800/70"><td className="px-4 py-3"><span className="inline-flex items-center gap-2 text-amber-300"><AlertTriangle size={13} />{issue.severity}</span></td><td className="font-mono text-slate-300">{issue.code}</td><td className="text-slate-500">{issue.entity_type} #{issue.entity_id}</td><td className="font-mono text-slate-500">{String(issue.context?.raw ?? '—')}</td><td>{issue.resolved_at ? <span className="inline-flex items-center gap-1 text-emerald-300"><CheckCircle2 size={13} />Resuelto</span> : <span className="text-amber-300">Pendiente</span>}</td></tr>)}</tbody></table></div></Card></>
}
