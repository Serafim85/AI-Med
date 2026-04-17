import { useEffect } from 'react'

import { fetchMe } from './api/auth'
import { AppRoutes } from './routes'
import { useAuthStore } from './store/auth'

export default function App() {
  const token = useAuthStore((s) => s.token)
  const bootstrapped = useAuthStore((s) => s.bootstrapped)
  const setUser = useAuthStore((s) => s.setUser)
  const markBootstrapped = useAuthStore((s) => s.markBootstrapped)
  const clear = useAuthStore((s) => s.clear)

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      if (!token) {
        markBootstrapped()
        return
      }
      try {
        const user = await fetchMe()
        if (!cancelled) {
          setUser(user)
          markBootstrapped()
        }
      } catch {
        if (!cancelled) {
          clear()
        }
      }
    }

    if (!bootstrapped) {
      void bootstrap()
    }

    return () => {
      cancelled = true
    }
  }, [token, bootstrapped, setUser, markBootstrapped, clear])

  return <AppRoutes />
}
