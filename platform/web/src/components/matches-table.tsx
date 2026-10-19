import type { Match } from '../types'
import { Card } from './ui/card'

function score(match: Match) {
  if (match.home_score === null || match.away_score === null) return '—'
  return `${match.home_score} : ${match.away_score}`
}
export function MatchesTable({ matches }: { matches: Match[] }) {
  return (
    <Card className="overflow-hidden lg:col-span-3">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">Market watch</h2>
          <p className="text-xs text-slate-500">Últimos partidos disponibles</p>
        </div>
        <button className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-cyan-400/40 hover:text-cyan-300">Ver todos</button>
      </div>
      <div className="overflow-x-auto" tabIndex={0} aria-label="Tabla desplazable de partidos">
        <table className="w-full min-w-[760px] text-left text-xs">
          <thead className="bg-slate-950/40 text-[10px] uppercase tracking-[0.14em] text-slate-500">
            <tr><th className="px-4 py-3">Competición</th><th>Partido</th><th>Jornada</th><th>Estado</th><th className="pr-4 text-right">Marcador</th></tr>
          </thead>
          <tbody>
            {matches.slice(0, 12).map((match) => (
              <tr key={match.id} className="border-t border-slate-800/70 text-slate-300 hover:bg-cyan-400/[0.025]">
                <td className="px-4 py-3 text-slate-500">{match.competition}</td>
                <td className="font-medium text-slate-200">{match.home_team} <span className="px-1 text-slate-600">vs</span> {match.away_team}</td>
                <td className="text-slate-500">{match.round_name ?? '—'}</td>
                <td><span className="rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[10px] text-slate-400">{match.status}</span></td>
                <td className="pr-4 text-right font-mono text-sm font-semibold text-cyan-300">{score(match)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
