import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import type { Competition } from '../types'
import { Card } from './ui/card'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

export function CoverageChart({ competitions }: { competitions: Competition[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const selected = [...competitions].sort((a, b) => b.match_count - a.match_count).slice(0, 10)
    chart.setOption({
      animationDuration: 450,
      grid: { left: 8, right: 16, top: 18, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#111827',
        borderColor: '#334155',
        textStyle: { color: '#e2e8f0' },
      },
      xAxis: {
        type: 'value',
        axisLabel: { color: '#64748b', fontFamily: 'JetBrains Mono' },
        splitLine: { lineStyle: { color: '#182131' } },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: selected.map((item) => item.name),
        axisLabel: { color: '#94a3b8', width: 120, overflow: 'truncate' },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [{
        type: 'bar',
        data: selected.map((item) => item.match_count),
        barWidth: 10,
        itemStyle: { color: '#22d3ee', borderRadius: [0, 5, 5, 0] },
      }],
    })
    const resize = new ResizeObserver(() => chart.resize())
    resize.observe(ref.current)
    return () => { resize.disconnect(); chart.dispose() }
  }, [competitions])

  return (
    <Card className="p-4 lg:col-span-2">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">Cobertura por competición</h2>
          <p className="text-xs text-slate-500">Partidos disponibles en el modelo canónico</p>
        </div>
        <span className="rounded border border-cyan-400/20 bg-cyan-400/5 px-2 py-1 font-mono text-[10px] text-cyan-300">LIVE DATA</span>
      </div>
      <div
        ref={ref}
        className="h-[330px] w-full"
        role="img"
        aria-label="Gráfico de partidos disponibles por competición"
      />
    </Card>
  )
}
