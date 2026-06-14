import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getProfile } from '../api/auth'

interface User {
  id: number
  username: string
  email: string
  role: string
  storage_quota: number
  storage_used: number
  is_active: boolean
  last_login_at?: string
  created_at: string
}

interface AuthContextType {
  user: User | null
  token: string | null
  setAuth: (token: string, user: User) => void
  logout: () => void
  refreshUser: () => Promise<void>
  loading: boolean
}

const AuthContext = createContext<AuthContextType>(null!)

export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const savedToken = localStorage.getItem('token')
    if (savedToken) {
      setToken(savedToken)
      getProfile()
        .then((res: any) => setUser(res.data))
        .catch(() => {
          localStorage.removeItem('token')
          localStorage.removeItem('user')
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const setAuth = useCallback((newToken: string, newUser: User) => {
    setToken(newToken)
    setUser(newUser)
    localStorage.setItem('token', newToken)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    localStorage.removeItem('token')
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const res: any = await getProfile()
      setUser(res.data)
    } catch {
      // ignore
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, setAuth, logout, refreshUser, loading }}>
      {children}
    </AuthContext.Provider>
  )
}
