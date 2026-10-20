import { useQuery } from '@tanstack/react-query'
import { CircleDollarSign } from 'lucide-react'
import { useState } from 'react'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

const percent = (value: number | null) => value === null ? '—' : `${(value * 100).toFixed(2)}%`

export function OddsPage() {
  const [matchId, setMatchId] = useState(0)
  const matches = useQuery({ queryKey: ['matches-odds'], queryFn: () => api.matches({ limit: 200 }) })
  const value = useQuery({
    queryKey: ['odds-value', matchId],
    queryFn: () => api.oddsValue(matchId),
    enabled: Boolean(matchId),
    retry: false,
  })
  return <>
    <div className="mb-5"><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Market intelligence</p><h2 className="mt-1 text-2xl font-semibold text-white">Cuotas y valor esperado</h2></div>
    <Card className="mb-4 p-4"><select aria-label="Partido para analizar cuotas" value={matchId} onChange={(event) => setMatchId(Number(event.target.value))} className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2.5 text-sm"><option value={0}>Selecciona un partido</option>{matches.data?.map((match) => <option key={match.id} value={match.id}>{match.home_team} vs {match.away_team} · {match.competition}</option>)}</select></Card>
    {value.isError && <Card className="p-5 text-sm text-amber-300">Aún no hay predicción o cuotas disponibles para este partido.</Card>}
    {value.data && <Card className="overflow-hidden"><div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3 text-sm font-semibold"><CircleDollarSign size={16} className="text-cyan-300" />Oportunidades · modelo {value.data.model_version}</div><div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-xs"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="px-4 py-3">Proveedor</th><th>Mercado</th><th>Selección</th><th>Cuota</th><th>Implícita justa</th><th>Modelo</th><th>EV</th><th>Edge</th></tr></thead><tbody>{value.data.markets.map((market) => <tr key={market.id} className="border-t border-slate-800/70"><td className="px-4 py-3">{market.provider}</td><td>{market.market_key}{market.line === null ? '' : ` ${market.line}`}</td><td>{market.selection_key}</td><td className="font-mono text-cyan-300">{market.decimal_odd.toFixed(2)}</td><td>{percent(market.fair_implied_probability)}</td><td>{percent(market.model_probability)}</td><td className={market.expected_value !== null && market.expected_value > 0 ? 'text-emerald-300' : 'text-slate-500'}>{percent(market.expected_value)}</td><td>{percent(market.edge)}</td></tr>)}</tbody></table></div></Card>}
  </>
}
