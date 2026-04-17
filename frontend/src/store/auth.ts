import { create } from 'zustand'

export const AUTH_TOKEN_KEY = 'auth_token'

export interface AuthUser {
  id: string
  email: string
  full_name: string
}

interface AuthState {
  token: string | null
  user: AuthUser | null
  bootstrapped: boolean
  setAuth: (params: { token: string; user: AuthUser }) => void
  setUser: (user: AuthUser) => void
  markBootstrapped: () => void
  clear: () => void
}

function readTokenFromStorage(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY)
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  token: readTokenFromStorage(),
  user: null,
  bootstrapped: false,
  setAuth: ({ token, user }) => {
    try {
      localStorage.setItem(AUTH_TOKEN_KEY, token)
    } catch {
      /* ignore */
    }
    set({ token, user, bootstrapped: true })
  },
  setUser: (user) => set({ user }),
  markBootstrapped: () => set({ bootstrapped: true }),
  clear: () => {
    try {
      localStorage.removeItem(AUTH_TOKEN_KEY)
    } catch {
      /* ignore */
    }
    set({ token: null, user: null, bootstrapped: true })
  },
}))
