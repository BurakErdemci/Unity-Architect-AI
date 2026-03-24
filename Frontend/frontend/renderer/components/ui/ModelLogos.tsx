import React from 'react';

interface ModelLogoProps {
  provider?: string;
  className?: string;
  size?: number;
}

export const ModelLogo: React.FC<ModelLogoProps> = ({ provider, className, size = 16 }) => {
  const p = provider?.toLowerCase() || '';

  // OpenAI Logo - Precision Swirl
  if (p.includes('openai')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M22.28 9.82a5.98 5.98 0 0 0-.51-4.91 6.05 6.05 0 0 0-6.51-2.9 6.07 6.07 0 0 0-5.28 2.17 6.05 6.05 0 0 0-4.39-.03 6.03 6.03 0 0 0-3.33 3.47 6.03 6.03 0 0 0 .61 5.07 5.98 5.98 0 0 0 .52 4.91 6.05 6.05 0 0 0 6.51 2.9 6.07 6.07 0 0 0 5.28-2.17 6.05 6.05 0 0 0 4.39.03 6.03 6.03 0 0 0 3.33-3.47 6.03 6.03 0 0 0-.61-5.07zm-10.28 8.2a3.69 3.69 0 0 1-1.9-.53l.12-.07 3.5-2a.75.75 0 0 0 .38-.65v-4.91a3.63 3.63 0 0 1 1.93 1.93v4.2a3.69 3.69 0 0 1-2.03 2zM4.55 15.77a3.69 3.69 0 0 1-.48-1.92v-3.49a.75.75 0 0 0-.38-.65l-3.5-2-.12-.07a3.69 3.69 0 0 1 2.38-1.11 3.63 3.63 0 0 1 1.93.16l-.01 4.02a.75.75 0 0 0 .38.65l3.5 2a3.69 3.69 0 0 1-3.7 2.4zM3.8 6.46a3.69 3.69 0 0 1 1.43-1.39l-.01.08v4.02a.75.75 0 0 0 .38.65l3.5 2v1.49a3.63 3.63 0 0 1-2.1-.16l-3.5-2a3.69 3.69 0 0 1 .3-4.7zm14.92 1.32a3.69 3.69 0 0 1 1.9.53l-.12.07-3.5 2a.75.75 0 0 0-.38.65v4.91a3.63 3.63 0 0 1-1.93-1.93V10.12a3.69 3.69 0 0 1 2.03-2zM21.23 11a3.69 3.69 0 0 1 .48 1.92v3.49a.75.75 0 0 0 .38.65l3.5 2 .12.07a3.69 3.69 0 0 1-2.38 1.11 3.63 3.63 0 0 1-1.93-.16l.01-4.02a.75.75 0 0 0-.38-.65l-3.5-2a3.69 3.69 0 0 1 3.7-2.4zm1.18 9.31a3.69 3.69 0 0 1-1.43 1.39l.01-.08v-4.02a.75.75 0 0 0-.38-.65l-3.5-2v-1.49a3.63 3.63 0 0 1 2.1.16l3.5 2a3.69 3.69 0 0 1-.3 4.7zM12 15.42a1.63 1.63 0 1 1 0-3.25 1.63 1.63 0 0 1 0 3.25z" />
      </svg>
    );
  }

  // Anthropic (Claude) Logo - Authentic Sunmark
  if (p.includes('anthropic') || p.includes('claude')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M11.996 0L10.744 6.836H13.248L11.996 0ZM7.34 2.148L9.088 8.796L11.532 7.848L8.796 2.148L7.34 2.148ZM3.516 5.86L6.598 11.23L8.852 9.535L5.86 3.516L3.516 5.86ZM1.41 10.744L5.86 13.918L7.34 11.637L2.148 8.652L1.41 10.744ZM1.41 15.256L5.86 12.082L7.34 14.363L2.148 17.348L1.41 15.256ZM3.516 20.141L6.598 14.77L8.852 16.465L5.86 20.484L3.516 20.141ZM7.34 23.852L9.088 17.204L11.532 18.152L8.796 23.852H7.34ZM11.996 24L13.248 17.164H10.744L11.996 24ZM16.652 21.852L14.904 15.204L12.46 16.152L15.196 21.852H16.652ZM20.484 18.141L17.402 12.77L15.148 14.465L18.141 20.484L20.484 18.141ZM22.59 13.256L18.141 10.082L16.66 12.363L21.852 15.348L22.59 13.256ZM22.59 8.744L18.141 11.918L16.66 9.637L21.852 6.652L22.59 8.744ZM20.484 3.859L17.402 9.23L15.148 7.535L18.141 3.516L20.484 3.859ZM16.652 0.148L14.904 6.796L12.46 5.848L15.196 0.148H16.652Z" />
      </svg>
    );
  }

  // Groq Logo
  if (p.includes('groq')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71L12 2z" />
      </svg>
    );
  }

  // Google (Gemini) Logo - 4-pointed star
  if (p.includes('google') || p.includes('gemini')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M12 0l2.5 9.5L24 12l-9.5 2.5L12 24l-2.5-9.5L0 12l9.5-2.5z" />
      </svg>
    );
  }

  // DeepSeek Logo
  if (p.includes('deepseek')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z" />
      </svg>
    );
  }

  // Moonshot (Kimi) Logo - Stylized Crescent
  if (p.includes('moonshot') || p.includes('openrouter')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z" />
      </svg>
    );
  }

  // Ollama Logo - Stylized Head
  if (p.includes('ollama')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8zm-1-11a1 1 0 1 1 2 0 1 1 0 0 1-2 0zm0 4a1 1 0 1 1 2 0 1 1 0 0 1-2 0z" />
      </svg>
    );
  }

  // Unity / KB Logo
  if (p.includes('kb') || p.includes('unity')) {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="currentColor">
        <path d="M12 0l12 6.928v13.856L12 27.712l-12-6.928V6.928L12 0zm0 2.31L2.31 7.91v11.892L12 25.402l9.69-5.6V7.91L12 2.31zM12 6.928l6.928 4v7.712l-6.928 4-6.928-4v-7.712l6.928-4z" />
      </svg>
    );
  }

  // Fallback Bot Icon (Lucide equivalent path)
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 8V4H8" /><rect width="16" height="12" x="4" y="8" rx="2" /><path d="M2 14h2" /><path d="M20 14h2" /><path d="M15 13v2" /><path d="M9 13v2" />
    </svg>
  );
};
