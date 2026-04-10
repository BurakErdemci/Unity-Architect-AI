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
  pipeline?: any;
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
  use_multi_agent: boolean;
  force_claude_coder: boolean;
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
