import { useQuery } from '@tanstack/react-query'
import { LogOut, UserRound } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { Card } from '../components/ui/card'
import { api } from '../lib/api'

export function AccountPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const token = window.localStorage.getItem('fais_access_token')
  const me = useQuery({ queryKey: ['me', revision], queryFn: api.me, enabled: Boolean(token), retry: false })
  const favorites = useQuery({ queryKey: ['favorites', revision], queryFn: api.favorites, enabled: Boolean(token), retry: false })
  const notifications = useQuery({ queryKey: ['notifications', revision], queryFn: api.notifications, enabled: Boolean(token), retry: false })

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      const result = mode === 'login' ? await api.login(email, password) : await api.register(email, password, name)
      window.localStorage.setItem('fais_access_token', result.access_token)
      setRevision((value) => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No fue posible autenticar')
    }
  }

  function logout() {
    window.localStorage.removeItem('fais_access_token')
    setRevision((value) => value + 1)
  }

  if (token && me.data) return <div className="grid gap-4 lg:grid-cols-2"><Card className="p-6"><div className="flex items-center gap-3"><div className="rounded-full bg-cyan-400/10 p-3 text-cyan-300"><UserRound /></div><div><h2 className="text-lg font-semibold text-white">{me.data.display_name}</h2><p className="text-xs text-slate-500">{me.data.email} · {me.data.role}</p></div></div><button onClick={logout} className="mt-6 inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-300"><LogOut size={14} />Cerrar sesión</button></Card><Card className="p-6"><h3 className="text-sm font-semibold">Preferencias</h3><p className="mt-2 text-xs text-slate-500">{favorites.data?.length ?? 0} favoritos guardados · {notifications.data?.filter((item) => !item.read_at).length ?? 0} notificaciones sin leer.</p><div className="mt-4 space-y-2">{notifications.data?.slice(0, 5).map((item) => <div key={item.id} className="rounded border border-slate-800 p-3"><p className="text-xs text-slate-300">{item.title}</p><p className="mt-1 font-mono text-[10px] text-slate-600">{item.created_at}</p></div>)}</div></Card></div>

  return <Card className="mx-auto max-w-md p-6"><p className="text-[10px] uppercase tracking-[0.2em] text-cyan-400">Secure workspace</p><h2 className="mt-2 text-xl font-semibold text-white">{mode === 'login' ? 'Iniciar sesión' : 'Crear cuenta'}</h2><form onSubmit={submit} className="mt-6 space-y-3">{mode === 'register' && <input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} placeholder="Nombre" className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-cyan-400/50" />}<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required placeholder="Correo" className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-cyan-400/50" /><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={10} placeholder="Contraseña (mínimo 10 caracteres)" className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-cyan-400/50" />{error && <p className="text-xs text-rose-300">{error}</p>}<button className="w-full rounded-md bg-cyan-400 px-3 py-2.5 text-sm font-semibold text-slate-950">Continuar</button></form><button onClick={() => setMode(mode === 'login' ? 'register' : 'login')} className="mt-4 text-xs text-slate-500 hover:text-cyan-300">{mode === 'login' ? 'Crear una cuenta nueva' : 'Ya tengo una cuenta'}</button></Card>
}
