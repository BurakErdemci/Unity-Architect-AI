import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import axios from 'axios';
import { AIConfig, AvailableModels, UserData } from '../../components/home/types';

export type UnityMCPStatus = 'off' | 'starting' | 'running' | 'connected';

export const useAIConfig = (API: string, user: UserData | null, showToast: (msg: string, type: any) => void, workspacePath?: string) => {
  const [aiConfig, setAiConfig] = useState<AIConfig>({
    provider_type: 'subscription', api_key: '', model_name: 'claude-sonnet-4-6', thinking_level: 'medium'
  });
  const [availableModels, setAvailableModels] = useState<AvailableModels>({ local: [], cloud: [], subscription: [] });
  const [providersWithKeys, setProvidersWithKeys] = useState<string[]>([]);
  const [modelOrToggles, setModelOrToggles] = useState<Record<string, boolean>>({});
  const [showSettings, setShowSettings] = useState(false);
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);

  // Unity MCP toggle
  const [unityMcpStatus, setUnityMcpStatus] = useState<UnityMCPStatus>('off');
  const [unityMcpToggling, setUnityMcpToggling] = useState(false);
  const [unityMcpError, setUnityMcpError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startingUntilRef = useRef<number>(0); // Toggle ON'dan itibaren 30s boyunca 'off' yanıtını yoksay
  const errorClearRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const fetchUnityMcpStatus = useCallback(async () => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/mcp/unity/status`);
      const status = res.data.status as UnityMCPStatus;

      // Toggle ON sonrası 30s içinde 'off' gelirse yoksay — sunucu henüz başlıyor olabilir
      if (status === 'off' && Date.now() < startingUntilRef.current) return;

      setUnityMcpStatus(status);
      if (status === 'connected') {
        stopPolling();
        pollRef.current = setInterval(fetchUnityMcpStatus, 15000);
      } else if (status === 'off') {
        // Kapalı ama yine de 8s'de bir kontrol et — Unity kendi başlatmış olabilir
        stopPolling();
        pollRef.current = setInterval(fetchUnityMcpStatus, 8000);
      }
      // 'starting' veya 'running' → mevcut hızlı interval devam eder
    } catch {
      // Hata olsa bile durumu 'off' yapma, sadece tekrar dene
      stopPolling();
      pollRef.current = setInterval(fetchUnityMcpStatus, 5000);
    }
  }, [API, stopPolling]);

  const toggleUnityMcp = useCallback(async () => {
    if (!API || unityMcpToggling) return;
    setUnityMcpToggling(true);
    const turningOn = unityMcpStatus === 'off';
    try {
      await axios.post(`${API}/mcp/unity/toggle`, { enabled: turningOn, workspace_path: workspacePath || null });
      if (turningOn) {
        setUnityMcpStatus('starting');
        startingUntilRef.current = Date.now() + 30000; // 30s boyunca 'off' yanıtını yoksay
        stopPolling();
        pollRef.current = setInterval(fetchUnityMcpStatus, 3000);
      } else {
        stopPolling();
        startingUntilRef.current = 0;
        setUnityMcpStatus('off');
        pollRef.current = setInterval(fetchUnityMcpStatus, 8000);
      }
    } catch (err: any) {
      const msg = err?.response?.status === 409
        ? (err.response.data?.detail || "Unity Editor açık değil. Lütfen önce Unity'yi açın.")
        : 'Unity MCP toggle başarısız.';
      showToast(msg, 'error');
      setUnityMcpError(msg);
      // 6 saniye sonra uyarıyı temizle
      if (errorClearRef.current) clearTimeout(errorClearRef.current);
      errorClearRef.current = setTimeout(() => setUnityMcpError(null), 6000);
      setUnityMcpStatus('off');
    } finally {
      setUnityMcpToggling(false);
    }
  }, [API, unityMcpStatus, unityMcpToggling, fetchUnityMcpStatus, stopPolling, showToast, workspacePath]);

  // Başlangıçta sorgula ve sürekli kontrol et
  useEffect(() => {
    if (!API) return;
    fetchUnityMcpStatus();
    // 8s'de bir otomatik kontrol — Unity kendi başlatmış olabilir
    pollRef.current = setInterval(fetchUnityMcpStatus, 8000);
    return () => stopPolling();
  }, [API]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchAIConfig = useCallback(async (userId: number) => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/get-ai-config/${userId}`);
      if (res.data) {
        setAiConfig({ ...res.data, api_key: '' });
        // Eğer backend'den bir api_key geldiyse (temizlenmeden önce), bu provider'ı listeye ekle
        if (res.data.api_key && !providersWithKeys.includes(res.data.provider_type)) {
          setProvidersWithKeys(prev => [...new Set([...prev, res.data.provider_type])]);
        }
      }
    } catch (err) { console.error("Config hatası:", err); }
  }, [API, providersWithKeys]);

  const fetchAvailableModels = useCallback(async () => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/available-models`);
      if (res.data) setAvailableModels(res.data);
    } catch (err) { console.error("Modeller alınamadı:", err); }
  }, [API]);

  const fetchProvidersWithKeys = useCallback(async (userId: number) => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/api-keys/${userId}`);
      if (res.data?.providers_with_keys) setProvidersWithKeys(res.data.providers_with_keys);
    } catch (err) { console.error("API keys hatası:", err); }
  }, [API]);

  const saveAIConfig = useCallback(async () => {
    if (!user || !API) return;
    try {
      const configToSave = { ...aiConfig, user_id: user.id };
      const isCloud = !['ollama', 'kb'].includes(configToSave.provider_type);

      if (!isCloud) configToSave.api_key = '';

      if (configToSave.api_key && isCloud) {
        await axios.post(`${API}/api-keys/save`, {
          user_id: user.id,
          provider_type: configToSave.provider_type,
          api_key: configToSave.api_key
        });
      }

      if (isCloud && !configToSave.api_key && !providersWithKeys.includes(configToSave.provider_type)) {
        showToast(`${configToSave.provider_type} için API key eksik!`, 'warning');
        return;
      }

      await axios.post(`${API}/save-ai-config`, configToSave);
      setAiConfig({ ...aiConfig, api_key: '' });
      await fetchProvidersWithKeys(user.id);
      showToast("Ayarlar kaydedildi!", 'success');
      setShowSettings(false);
    } catch (err) { showToast("Kaydedilemedi.", 'error'); }
  }, [API, aiConfig, fetchProvidersWithKeys, providersWithKeys, showToast, user]);

  const deleteApiKey = useCallback(async (provider: string) => {
    if (!user || !API) return;
    try {
      await axios.delete(`${API}/api-keys/${user.id}/${provider}`);
      await fetchProvidersWithKeys(user.id);
      setAiConfig(prev => ({ ...prev, api_key: '' }));
    } catch (err) {
      showToast('Key silinirken bir hata oluştu.', 'error');
    }
  }, [API, fetchProvidersWithKeys, showToast, user]);

  const effectiveProvider = useMemo(() => aiConfig.provider_type, [aiConfig.provider_type]);

  const displayModelName = useMemo(() => {
    if (!aiConfig.model_name) return 'Model Seçin';
    const allModels = [...availableModels.cloud, ...(availableModels.subscription || [])];
    const found = allModels.find(m =>
      m.id === aiConfig.model_name || (m as any).openrouter_id === aiConfig.model_name
    );
    if (found) return found.name;
    const name = aiConfig.model_name;
    // Dinamik CLI modelleri (cursor/opencode) statik listede yok → prefix'i soy.
    if (name.startsWith('cursor-')) return name.slice(7);
    if (name.startsWith('copilot-')) return name.slice(8);
    if (name.startsWith('opencode:')) {
      const m = name.slice(9);
      return m.includes('/') ? m.split('/').slice(1).join('/') : m;
    }
    if (name.includes('/')) return name.split('/').slice(1).join('/');
    return name;
  }, [aiConfig, availableModels]);

  return {
    aiConfig,
    setAiConfig,
    availableModels,
    providersWithKeys,
    modelOrToggles,
    setModelOrToggles,
    showSettings,
    setShowSettings,
    isModelDropdownOpen,
    setIsModelDropdownOpen,
    fetchAIConfig,
    fetchAvailableModels,
    fetchProvidersWithKeys,
    saveAIConfig,
    deleteApiKey,
    effectiveProvider,
    displayModelName,
    unityMcpStatus,
    unityMcpToggling,
    unityMcpError,
    toggleUnityMcp,
  };
};
