import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import type { User } from '../types'

export function RequireRole({ roles, children }: { roles: User['role'][]; children: ReactNode }) {
  const location = useLocation()
  const token = window.localStorage.getItem('fais_access_token')
  const me = useQuery({ queryKey: ['me', token], queryFn: api.me, enabled: Boolean(token), retry: false })

  if (!token) return <Navigate to="/account" replace state={{ from: location.pathname }} />
  if (me.isPending) return <p className="p-6 text-sm text-slate-500">Validando acceso…</p>
  if (me.isError || !me.data) return <Navigate to="/account" replace />
  if (!roles.includes(me.data.role)) return <Navigate to="/" replace />
  return children
}
