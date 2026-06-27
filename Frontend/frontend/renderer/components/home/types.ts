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
  tool_calls?: { tool: string; args: any; summary?: string; success?: boolean }[];
  tools?: { tool: string; args: any; summary?: string; success?: boolean }[];
  images?: string[];
  slashCommand?: string;  // 'usage' | 'cost' — özel kart olarak render edilen slash komutu yanıtı
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
