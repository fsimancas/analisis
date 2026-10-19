import type { LucideIcon } from 'lucide-react'
import { Card } from './ui/card'

interface MetricCardProps {
  label: string
  value: string
  detail: string
  icon: LucideIcon
  tone?: 'cyan' | 'violet' | 'emerald' | 'amber'
}
const tones = {
  cyan: 'text-cyan-300 bg-cyan-400/10 border-cyan-400/20',
  violet: 'text-violet-300 bg-violet-400/10 border-violet-400/20',
  emerald: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/20',
  amber: 'text-amber-300 bg-amber-400/10 border-amber-400/20',
}

export function MetricCard({ label, value, detail, icon: Icon, tone = 'cyan' }: MetricCardProps) {
  return (
    <Card className="group p-4 transition-colors hover:border-slate-600/70">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
          <p className="mt-2 font-mono text-2xl font-semibold tracking-tight text-slate-100">{value}</p>
        </div>
        <div className={`rounded-lg border p-2 ${tones[tone]}`}><Icon size={16} /></div>
      </div>
      <p className="mt-3 text-xs text-slate-500">{detail}</p>
    </Card>
  )
}
