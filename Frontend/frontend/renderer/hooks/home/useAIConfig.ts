import { useState, useCallback, useEffect, useMemo } from 'react';
import axios from 'axios';
import { AIConfig, AvailableModels, UserData } from '../../components/home/types';

export const useAIConfig = (API: string, user: UserData | null, showToast: (msg: string, type: any) => void) => {
  const [aiConfig, setAiConfig] = useState<AIConfig>({
    provider_type: 'kb', api_key: '', model_name: 'unity-kb-v1', use_multi_agent: true
  });
  const [availableModels, setAvailableModels] = useState<AvailableModels>({ local: [], cloud: [] });
  const [providersWithKeys, setProvidersWithKeys] = useState<string[]>([]);
  const [modelOrToggles, setModelOrToggles] = useState<Record<string, boolean>>({});
  const [showSettings, setShowSettings] = useState(false);
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);

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
    const found = availableModels.cloud.find(m =>
      m.id === aiConfig.model_name || m.openrouter_id === aiConfig.model_name
    );
    if (found) return found.name;
    const name = aiConfig.model_name;
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
    displayModelName
  };
};
