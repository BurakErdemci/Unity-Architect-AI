import React, { useEffect, useMemo, useRef, useState } from 'react'
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

// Stable references for objects/functions that never change
const STABLE_AUTH_FORM = { username: '', password: '', email: '' }
const STABLE_OAUTH_PROVIDERS = { google: false, github: false }
const noop = () => {}
const noopAsync = async () => {}
const noopAuthSubmit = async (_e: React.FormEvent<HTMLFormElement>, _rememberMe: boolean) => {}
const noopOAuth = async (_provider: 'google' | 'github') => {}
const noopSetAuthMode = (_mode: 'login' | 'register') => {}

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

  // Memoize user object so it's only recreated when sessionToken changes
  const user = useMemo(() => ({ ...BASE_LOCAL, sessionToken }), [sessionToken])

  return {
    user,
    isAuthenticated: true,
    isLoading: !ready,
    authMode: 'login' as const,
    setAuthMode: noopSetAuthMode,
    authForm: STABLE_AUTH_FORM,
    authNotice: null as string | null,
    setAuthNotice: noop,
    oauthProviders: STABLE_OAUTH_PROVIDERS,
    performLogout: noop,
    hydrateSession: noopAsync,
    handleAuthSubmit: noopAuthSubmit,
    handleOAuth: noopOAuth,
    fetchAuthProviders: noopAsync,
    authAlertShownRef,
  }
}
