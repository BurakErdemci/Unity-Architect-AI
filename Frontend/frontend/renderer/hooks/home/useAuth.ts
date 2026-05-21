import React, { useEffect, useRef, useState } from 'react'
import axios from 'axios'

export interface User {
  id: number
  email: string
  username: string
  name: string
  sessionToken: string
}

const BASE_LOCAL: Omit<User, 'sessionToken'> = {
  id: 1, email: 'local@localhost', username: 'local', name: 'local',
}

export function useAuth(_API: string, backendReady: boolean) {
  const [sessionToken, setSessionToken] = useState<string>('local')
  const [ready, setReady] = useState(false)
  const authAlertShownRef = useRef(false)

  useEffect(() => {
    if (!backendReady) return
    const init = async () => {
      let token = 'local'
      try {
        token = await (window as any).ipc.invoke('app-token-get')
      } catch { /* dev mode — no IPC available */ }
      setSessionToken(token)
      axios.defaults.headers.common['X-Session-Token'] = token
      setReady(true)
    }
    init()
  }, [backendReady])

  return {
    user: { ...BASE_LOCAL, sessionToken },
    isAuthenticated: true,
    isLoading: !ready,
    authMode: 'login' as const,
    setAuthMode: (_mode: 'login' | 'register') => {},
    authForm: { username: '', password: '', email: '' },
    authNotice: null as string | null,
    setAuthNotice: () => {},
    oauthProviders: { google: false, github: false },
    performLogout: () => {},
    hydrateSession: async () => {},
    handleAuthSubmit: async (_e: React.FormEvent<HTMLFormElement>, _rememberMe: boolean) => {},
    handleOAuth: async (_provider: 'google' | 'github') => {},
    fetchAuthProviders: async () => {},
    authAlertShownRef,
  }
}
