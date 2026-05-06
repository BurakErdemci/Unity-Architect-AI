import { useState, useCallback, useRef, useEffect } from 'react';
import axios from 'axios';
import { UserData } from '../../components/home/types';

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

export const useAuth = (API: string, backendReady: boolean) => {
  const [user, setUser] = useState<UserData | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authForm, setAuthForm] = useState({ username: '', password: '' });
  const [authNotice, setAuthNotice] = useState<string | null>(null);
  const [oauthProviders, setOauthProviders] = useState({ google: false, github: false });
  
  const userRef = useRef<UserData | null>(null);
  const authAlertShownRef = useRef(false);

  useEffect(() => {
    userRef.current = user;
  }, [user]);


  const setSessionTokenHeader = useCallback((token: string | null) => {
    if (token) {
      axios.defaults.headers.common['X-Session-Token'] = token;
    } else {
      delete axios.defaults.headers.common['X-Session-Token'];
    }
  }, []);

  const persistSessionToken = useCallback(async (sessionToken: string) => {
    const persisted = await ipc?.invoke('session-set', sessionToken).catch(() => false);
    return persisted === true;
  }, []);

  const hydrateSession = useCallback(async (sessionToken: string, persistSession: boolean) => {
    setSessionTokenHeader(sessionToken);
    try {
      const res = await axios.get(`${API}/me`);
      const userData = {
        id: res.data.user_id,
        name: res.data.username,
        sessionToken,
      };
      setUser(userData);
      setAuthNotice(null);
      if (persistSession) {
        await persistSessionToken(sessionToken);
      } else {
        await ipc?.invoke('session-clear').catch(() => undefined);
      }
      return userData;
    } catch (err) {
      setSessionTokenHeader(null);
      ipc?.invoke('session-clear').catch(() => undefined);
      setUser(null);
      throw err;
    }
  }, [API, persistSessionToken, setSessionTokenHeader]);

  // --- Auto-Hydrate Session ---
  useEffect(() => {
    if (backendReady && API && !user && !authAlertShownRef.current) {
      ipc?.invoke('session-get').then(async (token: string | null) => {
        if (token) {
          try {
            await hydrateSession(token, true);
          } catch (err) {
            console.error("Session restoration failed:", err);
          }
        }
      });
      authAlertShownRef.current = true;
    }
  }, [backendReady, API, user, hydrateSession]);

  const performLogout = useCallback(() => {
    if (userRef.current?.sessionToken) {
      axios.post(`${API}/logout`).catch(() => undefined);
    }
    setUser(null);
    userRef.current = null;
    setSessionTokenHeader(null);
    ipc?.invoke('session-clear').catch(() => undefined);
  }, [API, setSessionTokenHeader]);

  const fetchAuthProviders = useCallback(async () => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/auth/providers`);
      if (res.data) setOauthProviders({
        google: Boolean(res.data.google),
        github: Boolean(res.data.github),
      });
    } catch (err) {
      setOauthProviders({ google: false, github: false });
    }
  }, [API]);

  const handleAuthSubmit = async (event: React.FormEvent<HTMLFormElement>, rememberMe: boolean) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const username = formData.get('username') as string;
    const password = formData.get('password') as string;

    if (!username || !password) {
      setAuthNotice("Kullanıcı adı ve şifre alanlarını doldurun.");
      return;
    }

    if (!backendReady || !API) {
      setAuthNotice("Backend henüz hazır değil. Lütfen birkaç saniye sonra tekrar deneyin.");
      return;
    }

    setAuthForm({ username, password });
    setAuthNotice(null);

    const url = authMode === 'login' ? '/login' : '/register';
    try {
      const res = await axios.post(`${API}${url}`, { username, password });
      if (authMode === 'login') {
        await hydrateSession(res.data.session_token, rememberMe);
      } else {
        setAuthNotice("Kayıt oluşturuldu. Şimdi giriş yapabilirsiniz.");
        setAuthMode('login');
      }
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 429) {
        setAuthNotice("Çok fazla giriş denemesi yapıldı.");
      } else if (authMode === 'login') {
        setAuthNotice("Giriş yapılamadı. Bilgilerinizi kontrol edin.");
      } else {
        setAuthNotice("Kayıt işlemi tamamlanamadı.");
      }
    }
  };

  const handleOAuth = async (provider: 'google' | 'github') => {
    setAuthNotice(null);
    if (!backendReady || !API) {
      setAuthNotice("Backend henüz hazır değil.");
      return;
    }
    try {
      const res = await axios.get(`${API}/auth/${provider}/url`);
      const oauthUrl = res.data.url;
      const popup = window.open(oauthUrl, `${provider}_oauth`, 'width=500,height=700');
      if (!popup) {
        setAuthNotice("Popup engellendi.");
        return;
      }

      const handler = (event: MessageEvent) => {
        if (event.origin !== API || event.source !== popup) return;

        if (event.data?.type === 'oauth-complete' && typeof event.data.code === 'string') {
          window.removeEventListener('message', handler);
          axios.post(`${API}/auth/complete/${event.data.code}`)
            .then(async (completeRes) => {
              await hydrateSession(completeRes.data.session_token, true);
            })
            .catch(() => {
              setAuthNotice("Giriş tamamlanamadı.");
            });
        }
      };
      window.addEventListener('message', handler);
    } catch (err) {
      setAuthNotice("Giriş başlatılamıyor.");
    }
  };

  return {
    user,
    setUser,
    authMode,
    setAuthMode,
    authForm,
    authNotice,
    setAuthNotice,
    oauthProviders,
    performLogout,
    hydrateSession,
    handleAuthSubmit,
    handleOAuth,
    fetchAuthProviders,
    authAlertShownRef
  };
};
