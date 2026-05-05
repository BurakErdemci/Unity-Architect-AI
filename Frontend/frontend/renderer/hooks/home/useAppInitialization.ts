import { useState, useEffect, useCallback } from 'react';
import { useToast } from '../../components/ui/Toast';

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

export const useAppInitialization = () => {
  const [API, setAPI] = useState('');
  const [backendReady, setBackendReady] = useState(false);
  const [backendError, setBackendError] = useState(false);
  const { toasts, showToast, dismissToast } = useToast();

  useEffect(() => {
    const loadBackendBaseUrl = async () => {
      try {
        let baseUrl = ipc ? await ipc.invoke('get-backend-base-url') : '';
        if (!baseUrl) throw new Error('Backend URL alınamadı.');
        if (baseUrl.endsWith('/')) baseUrl = baseUrl.slice(0, -1);
        setAPI(baseUrl);
        setBackendReady(true);
      } catch (err) {
        setBackendReady(false);
        setBackendError(true);
      }
    };
    loadBackendBaseUrl();
  }, []);

  return {
    API,
    backendReady,
    backendError,
    toasts,
    showToast,
    dismissToast
  };
};
