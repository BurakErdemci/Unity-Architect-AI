import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import axios from 'axios';
import { AIConfig, AvailableModels, UserData } from '../../components/home/types';

/**
 * Backend'in `GET /mcp/unity/status` sözleşmesi (`unity_mcp_manager.get_status`).
 *
 * `blocked` = 8080'i dinleyen biri var ama BİZ DEĞİL — kimlik testi (kimliksiz
 * `POST /mcp` → 401 + kendi izlerimiz) yabancı olduğunu söyledi. `off`tan ayrı
 * bir durum olması şart: `off` bir "aç" davetidir, `blocked` ise kullanıcıdan
 * BAŞKA bir eylem ister (çakışan sunucuyu kapatmak) ve toggle'a basmak
 * sunucumuzu başlatmıyor.
 *
 * `unknown` = son yoklama BAŞARISIZ oldu, durum artık bilinmiyor (bulgu I-2,
 * 30 Tem 2026). Üçünden de ayrı bir durum olması şart:
 *
 *   • `connected` DEĞİL — çünkü ölçüm yok. Eski davranış son başarılı ölçümü
 *     korumaktı ve ölçüldü: backend çöktükten sonra bile gösterge SÜRESİZ
 *     yeşil kalıyordu. K1/c'nin bütün varlık sebebi yabancı sunucu tespiti;
 *     tespit sonucu kullanıcıya ulaşmıyorsa yapılan azaltma etkisiz.
 *   • `off` DEĞİL — o bir "aç" daveti ve geçici bir ağ hatasında kullanıcıyı
 *     sunucusu kapanmış sanmaya iter. Eski `catch` yorumu bu yüzden durumu
 *     `off` yapmıyordu ve o kısım HAKLIYDI; eksik olan üçüncü seçenekti.
 *   • `blocked` DEĞİL — o, kimlik testinin YABANCI dediği ölçülmüş bir sonuç.
 */
export type UnityMCPStatus = 'off' | 'blocked' | 'starting' | 'running' | 'connected' | 'unknown';

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
  // `blocked` sebebi. `unityMcpError` GEÇİCİ (bir toggle denemesinin sonucu, 6 sn
  // sonra siliniyor); bu KALICI, çünkü durumun kendisiyle yaşıyor: port
  // başkasındayken sebep ekranda durmalı, yoksa kullanıcı 6 saniye sonra elinde
  // yalnız gri bir düğmeyle kalıyor.
  const [unityMcpReason, setUnityMcpReason] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Yoklama kuşağı sayacı + montaj bayrağı; ikisi de `fetchUnityMcpStatus`'ta
  // kullanılıyor, gerekçe orada.
  const fetchNesilRef = useRef(0);
  const mountedRef = useRef(true);
  const startingUntilRef = useRef<number>(0); // Toggle ON'dan itibaren 30s boyunca 'off' yanıtını yoksay
  const errorClearRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const fetchUnityMcpStatus = useCallback(async () => {
    if (!API) return;
    // Yoklama kuşağı. İki ölçülmüş arızayı birden kapatıyor (doğrulama turu,
    // 30 Tem 2026):
    //
    //   1. ESKİ SONUÇ YENİYİ EZİYOR — iki yoklama uçuştayken önce başlayan
    //      sonra dönebiliyor ve bayat durumu geri yazıyor.
    //   2. TEMİZLİKTEN SONRA INTERVAL DİRİLİYOR — `useEffect` cleanup'ı
    //      `stopPolling()` çağırıyor ama uçuştaki istek iptal edilmiyor; o
    //      çözüldüğünde `catch`/`then` dalları YENİ bir `setInterval` kuruyor
    //      ve yoklama unmount'tan sonra sonsuza kadar sürüyordu.
    //
    // İkinci arızayı Faz 4 açtı: `catch` dalı eskiden yalnız interval
    // kuruyordu, şimdi `setState` de yapıyor — yani yaşayan bir sızıntıydı ve
    // düzeltme onu görünür hale getirdi.
    const nesil = ++fetchNesilRef.current;
    const guncelMi = () => nesil === fetchNesilRef.current && mountedRef.current;
    try {
      const res = await axios.get(`${API}/mcp/unity/status`);
      if (!guncelMi()) return;
      const status = res.data.status as UnityMCPStatus;
      const reason = typeof res.data?.reason === 'string' ? res.data.reason : null;

      // Toggle ON sonrası 30s içinde 'off' gelirse yoksay — sunucu henüz başlıyor olabilir.
      // `blocked` bu yutmanın DIŞINDA bırakıldı: o bir gecikme değil, kullanıcının
      // müdahalesini bekleyen bir çakışma; 30 sn susmak yalnız teşhisi geciktirir.
      if (status === 'off' && Date.now() < startingUntilRef.current) return;

      setUnityMcpStatus(status);
      // Sebep backend'de yalnız `blocked` dalında dolu. Başka durumda taşımak
      // bayat bir uyarıyı ekranda bırakırdı — kullanıcı çakışan sunucuyu
      // kapattıktan sonra bile "port başkasında" yazmaya devam ederdi.
      setUnityMcpReason(status === 'blocked' ? reason : null);
      if (status === 'connected') {
        stopPolling();
        pollRef.current = setInterval(fetchUnityMcpStatus, 15000);
      } else if (status === 'off' || status === 'blocked') {
        // Kapalı ama yine de 8s'de bir kontrol et — Unity kendi başlatmış olabilir.
        // `blocked` aynı ritimde: kullanıcı çakışan sunucuyu kapatınca durum
        // kendi kendine toparlanmalı, bir düğmeye basmaya gerek kalmadan.
        // ⚠️ Bu satırın `blocked` kısmı TEST EDİLMEDİ (ölçüldü 2026-07-30:
        // mutasyon kaçtı). Tek davranışsal farkı `connected` → `blocked`
        // geçişinde yoklamanın 15 sn yerine 8 sn olması, yani ~7 sn daha hızlı
        // toparlanma; sürmesi fake timer + interval sayacı ister ve kullanıcı
        // farkı görmez. Bilinçli boşluk, bulunmamış boşluk değil.
        stopPolling();
        pollRef.current = setInterval(fetchUnityMcpStatus, 8000);
      }
      // 'starting' veya 'running' → mevcut hızlı interval devam eder
    } catch {
      if (!guncelMi()) return;
      // Durum artık BİLİNMİYOR. Eskiden burada yalnız yoklama aralığı
      // değişiyordu ve son başarılı ölçüm olduğu gibi kalıyordu — ölçüldü
      // (bulgu I-2): backend çöktükten sonra bile gösterge süresiz `connected`
      // gösteriyordu. Yalan söyleyen bir gösterge, göstergesizlikten kötü.
      //
      // `off` yapılmıyor: o bir "aç" daveti ve geçici bir ağ hatasında
      // kullanıcıyı sunucusu kapanmış sanmaya iter. Eski yorumun bu kısmı
      // haklıydı; eksik olan "bilinmiyor" seçeneğiydi.
      setUnityMcpStatus('unknown');
      setUnityMcpReason(null);
      stopPolling();
      pollRef.current = setInterval(fetchUnityMcpStatus, 5000);
    }
  }, [API, stopPolling]);

  const toggleUnityMcp = useCallback(async () => {
    if (!API || unityMcpToggling) return;
    setUnityMcpToggling(true);
    // `blocked` de bir AÇMA denemesidir: kullanıcı çakışan sunucuyu kapattıysa
    // tek yolu bu düğme. Eskiden koşul `=== 'off'` olduğu için blocked'da
    // KAPATMA isteği gidiyordu; backend yabancı süreci öldürmediği için
    // sessizce 200 {"status":"stopped"} dönüyordu — yani kullanıcı butona
    // basıyor, hiçbir şey olmuyor ve bir hata bile görünmüyordu.
    const turningOn = unityMcpStatus === 'off' || unityMcpStatus === 'blocked';
    // Toggle da yoklama kuşağının İÇİNDE olmalı (2. doğrulama turu bulgusu).
    // İlk düzeltme yalnız `fetchUnityMcpStatus`'ı korumuştu; bu yol `await`
    // sonrası hem `setState` yapıyor hem `setInterval` kuruyordu, yani unmount
    // sırasında POST uçuştaysa temizlikten sonra yoklama yeniden doğuyordu.
    // Ayrıca kuşağı burada İLERLETMEK şart: toggle'dan ÖNCE başlamış bir
    // durum sorgusu, toggle'ın yazdığı `starting`/`off`'u ezebiliyordu.
    const nesil = ++fetchNesilRef.current;
    const guncelMi = () => nesil === fetchNesilRef.current && mountedRef.current;
    try {
      await axios.post(`${API}/mcp/unity/toggle`, { enabled: turningOn, workspace_path: workspacePath || null });
      if (!guncelMi()) return;
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
      if (!guncelMi()) return;
      // `detail` artık HER durum kodunda okunuyor. 500'ün gövdesi portu tutan
      // sürecin ADINI taşıyor (`unity_mcp_manager._blocked_reason`) ve eskiden
      // sabit bir "toggle başarısız" metniyle eziliyordu: sebep üretiliyor ama
      // kullanıcıya hiç ulaşmıyordu.
      const detail = err?.response?.data?.detail;
      // Tip kontrolü kozmetik değil, çökme kapısı: FastAPI doğrulama hatası
      // `detail`'i bir DİZİ döndürüyor ve dizi doğrudan render edilirse React
      // "Objects are not valid as a React child" ile düşüyor.
      const msg = typeof detail === 'string' && detail.trim()
        ? detail
        : err?.response?.status === 409
          ? "Unity Editor açık değil. Lütfen önce Unity'yi açın."
          : 'Unity MCP toggle başarısız.';
      showToast(msg, 'error');
      setUnityMcpError(msg);
      // 6 saniye sonra uyarıyı temizle
      if (errorClearRef.current) clearTimeout(errorClearRef.current);
      errorClearRef.current = setTimeout(() => setUnityMcpError(null), 6000);
      // Durumu TAHMİN etmiyoruz, ÖLÇÜYORUZ. Eskiden koşulsuz 'off' yazılıyordu;
      // port başkasındayken bu yanlış bilgi: kullanıcı gri "kapalı" görüyor,
      // aynı düğmeye basıyor ve sebebi hiç öğrenmiyor.
      await fetchUnityMcpStatus();
    } finally {
      setUnityMcpToggling(false);
    }
  }, [API, unityMcpStatus, unityMcpToggling, fetchUnityMcpStatus, stopPolling, showToast, workspacePath]);

  // Başlangıçta sorgula ve sürekli kontrol et
  useEffect(() => {
    if (!API) return;
    mountedRef.current = true;
    fetchUnityMcpStatus();
    // 8s'de bir otomatik kontrol — Unity kendi başlatmış olabilir
    pollRef.current = setInterval(fetchUnityMcpStatus, 8000);
    return () => {
      // Kuşağı ilerletmek uçuştaki isteğin dönüşünü ETKİSİZ kılıyor: `stopPolling`
      // tek başına yetmiyordu, çünkü çözülen istek yeni bir interval kuruyordu.
      mountedRef.current = false;
      fetchNesilRef.current++;
      stopPolling();
    };
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

  // ⚠️ `user?.sessionToken` bağımlılıkta OLMAK ZORUNDA. Eskiden yalnız `[API]`
  // vardı ve fonksiyon ilk render'ın `user`'ına kilitleniyordu; o anda token
  // henüz `useAuth`'un başlangıç değeri olan `'local'` (IPC `app-token-get`
  // sonradan çözülüyor). Sonuç ÖLÇÜLDÜ: istek daima `X-Session-Token: local`
  // ile gidiyor, `_check_token` 401 veriyor, `catch` sessizce yutuyor ve
  // `availableModels` sonsuza kadar boş kalıyor.
  //
  // Kullanıcıya yansıması: BÜTÜN bulut/API modelleri listeden kayboluyor
  // (bölüm `cloudGroups.length > 0` ile gizleniyor) ve `dynamic` alanı olmayan
  // CLI grupları — Claude Code, Antigravity, Kimi — boş açılıyor. Kendi
  // `/cli-models/{cli}` ucundan besleneni (codex/copilot/cursor/opencode)
  // etkilenmiyordu; arızayı bu kadar kafa karıştırıcı yapan da o asimetriydi.
  //
  // Açık başlık `axios.defaults.headers.common`daki DOĞRU değeri de eziyor,
  // yani genel varsayılan burada kurtarıcı olamıyor.
  const fetchAvailableModels = useCallback(async () => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/available-models`, { headers: { 'X-Session-Token': user?.sessionToken ?? '' } });
      if (res.data) setAvailableModels(res.data);
    } catch (err) { console.error("Modeller alınamadı:", err); }
  }, [API, user?.sessionToken]);

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
    unityMcpReason,
    toggleUnityMcp,
    // Durumu dışarıdan tazelemek için. İki tüketicisi var ve ikisi de aynı
    // soruyu soruyor: "şu an gerçekten ne durumda" — hata sonrası ölçüm, ve
    // testlerin "kullanıcı çakışan sunucuyu kapattı" senaryosu.
    refreshUnityMcpStatus: fetchUnityMcpStatus,
  };
};
