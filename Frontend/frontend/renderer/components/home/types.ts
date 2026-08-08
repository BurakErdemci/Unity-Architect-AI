export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  openrouter_id?: string;
  paid?: boolean;
}

export interface AvailableModels {
  local: ModelInfo[];
  cloud: ModelInfo[];
  subscription: ModelInfo[];
}

export interface UserData {
  id: number;
  name: string;
  sessionToken: string;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

// Chat'teki araç chip'i: args = araç girdisi (PARAMETRELER), output = araç sonucu (ÇIKTI),
// id = tool_use_id (sonucu doğru chip'e bağlamak için).
export interface ToolCallEntry {
  tool: string;
  args?: any;
  summary?: string;
  success?: boolean;
  output?: string;
  id?: string;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  smells: any[];
  timestamp: string;
  provider?: string;
  is_refined?: boolean;
  thinking?: string | null;
  thinking_duration_ms?: number | null;
  tool_calls?: ToolCallEntry[];
  tools?: ToolCallEntry[];
  images?: string[];
  slashCommand?: string;  // 'usage' | 'cost' — özel kart olarak render edilen slash komutu yanıtı
  // Tur sonu istatistiği (backend turn_usage event'i) — mesaj altında küçük özet satırı
  usage?: { input_tokens?: number; output_tokens?: number; cost_usd?: number | null; duration_ms?: number | null };
}

// Canlı aktivite göstergesi (backend status event'leri): Claude'un o an ne yaptığı +
// tur boyunca üretilen token. loading sırasında ChatPanel'de spinner satırı olarak görünür.
export interface ChatActivity {
  detail: string;
  tokens?: number;
}

export interface FileEntry {
  name: string;
  path: string;
  isDirectory: boolean;
  extension: string;
}

export interface AIConfig {
  provider_type: string;
  api_key: string;
  model_name: string;
  thinking_level: 'low' | 'medium' | 'high' | 'off';
  has_key?: boolean;
}

/** `/provider-ready` yanıtı — sohbet kapısının girdisi.
 *
 * `needs` bilerek bir KOD, cümle değil: backend'in çeviri mekanizması yok ve
 * oraya metin koymak ~300 sabit Türkçe metinlik borcu büyütürdü. Kullanıcıya
 * görünen metin `i18n.tsx`'teki `gate.needs.*` anahtarlarından geliyor.
 */
export interface ProviderReady {
  ready: boolean;
  kind: 'api' | 'cli' | 'local';
  provider: string;
  needs: null | 'apikey' | 'install' | 'login' | 'service';
}

export interface ExportFileEntry {
  name: string;
  code: string;
  path: string;
}

export interface ExportModalState {
  isOpen: boolean;
  codeString: string;
  suggestedName: string;
  targetDir: string;
  existingFile: boolean;
  multiFile: boolean;
  files: ExportFileEntry[];
  exportResult: { success: boolean; message: string } | null;
}

export type GenerationMode = 'auto' | 'step';
