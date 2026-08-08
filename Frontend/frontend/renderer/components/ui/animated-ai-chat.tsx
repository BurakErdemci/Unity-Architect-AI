"use client";

import { useEffect, useRef, useCallback, useTransition, useMemo } from "react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import {
    FileUp,
    CircleUserRound,
    ArrowUpIcon,
    Paperclip,
    PlusIcon,
    SendIcon,
    XIcon,
    Square,
    Sparkles,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import * as React from "react"
import { SkillsGallery, CommandMeta } from "../home/SkillsGallery";

interface UseAutoResizeTextareaProps {
    minHeight: number;
    maxHeight?: number;
}

function useAutoResizeTextarea({
    minHeight,
    maxHeight,
}: UseAutoResizeTextareaProps) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const adjustHeight = useCallback(
        (reset?: boolean) => {
            const textarea = textareaRef.current;
            if (!textarea) return;

            if (reset) {
                textarea.style.height = `${minHeight}px`;
                return;
            }

            textarea.style.height = `${minHeight}px`;
            const newHeight = Math.max(
                minHeight,
                Math.min(
                    textarea.scrollHeight,
                    maxHeight ?? Number.POSITIVE_INFINITY
                )
            );

            textarea.style.height = `${newHeight}px`;
        },
        [minHeight, maxHeight]
    );

    useEffect(() => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = `${minHeight}px`;
        }
    }, [minHeight]);

    useEffect(() => {
        const handleResize = () => adjustHeight();
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, [adjustHeight]);

    return { textareaRef, adjustHeight };
}

interface CommandSuggestion {
    icon: React.ReactNode;
    label: string;
    description: string;
    prefix: string;
    isSkill?: boolean;  // backend 'skills' listesinde mi (palette'te rozet için)
}

interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  containerClassName?: string;
  showRing?: boolean;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, containerClassName, showRing = true, ...props }, ref) => {
    const [isFocused, setIsFocused] = React.useState(false);
    
    return (
      <div className={cn(
        "relative",
        containerClassName
      )}>
        <textarea
          className={cn(
            "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
            "transition-all duration-200 ease-in-out",
            "placeholder:text-muted-foreground",
            "disabled:cursor-not-allowed disabled:opacity-50",
            showRing ? "focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0" : "",
            className
          )}
          ref={ref}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          {...props}
        />
        
        {showRing && isFocused && (
          <motion.span 
            className="absolute inset-0 rounded-md pointer-events-none ring-2 ring-offset-0 ring-violet-500/30"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
        )}

        {props.onChange && (
          <div 
            className="absolute bottom-2 right-2 opacity-0 w-2 h-2 bg-violet-500 rounded-full"
            style={{
              animation: 'none',
            }}
            id="textarea-ripple"
          />
        )}
      </div>
    )
  }
)
Textarea.displayName = "Textarea"

export function AnimatedChatInput({
    value,
    setValue,
    onSendMessage,
    onCommand,
    onStop,
    onFileDrop,
    isLoading,
    // Varsayılanlar yalnız SON ÇARE: çağrı yerleri metni i18n'den geçiriyor.
    // Eskiden burada "Ask zap a question..." yazıyordu — başka bir ürünün
    // şablonundan kalmış bir metin, ve kullanıcının ilk yazacağı yerde duruyordu.
    placeholder = "Type a message...",
    className,
    disabled = false,
    disabledPlaceholder = "Unavailable",
    slashCommands = [],
    skills = [],
    commandMeta = [],
    galleryProvider = 'claude'
}: {
    value: string;
    setValue: (val: string) => void;
    onSendMessage: (val: string, images?: string[], videos?: any[]) => void;
    onCommand?: (cmd: string) => boolean;
    onStop?: () => void;
    onFileDrop?: (entry: { path: string, name: string }) => void;
    isLoading: boolean;
    placeholder?: string;
    className?: string;
    disabled?: boolean;
    disabledPlaceholder?: string;
    slashCommands?: string[];  // backend'den gelen Claude Code slash komutları (isimler, '/'siz)
    skills?: string[];         // slash komutlarının skill olan alt kümesi (rozet için)
    commandMeta?: CommandMeta[];  // {name, description, argumentHint, insert?} — Skills galerisi için
    galleryProvider?: string;     // 'claude' | 'codex' | 'agy' — galeri gösterim/insert davranışı
}) {
    // Typing state is INTERNAL — does not propagate to parent on every keystroke.
    const [internalValue, setInternalValue] = useState(value);
    const [attachments, setAttachments] = useState<{ name: string, data: string, type: 'image' | 'file' | 'video', path?: string, url?: string }[]>([]);
    const [activeSuggestion, setActiveSuggestion] = useState<number>(-1);
    const [showCommandPalette, setShowCommandPalette] = useState(false);
    const { textareaRef, adjustHeight } = useAutoResizeTextarea({
        minHeight: 60,
        maxHeight: 200,
    });
    const [inputFocused, setInputFocused] = useState(false);
    const [showSkillsGallery, setShowSkillsGallery] = useState(false);
    const commandPaletteRef = useRef<HTMLDivElement>(null);
    const galleryRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Galeriden seçim: hazır metin (Claude: '/<isim> '; Codex: skill defaultPrompt'u)
    // girdiye yazılır, kullanıcı (gerekirse düzenleyip) Enter'a basar — yıkıcı komutların
    // kazara tetiklenmemesi için otomatik GÖNDERİLMEZ.
    const handleSelectCommand = (insertText: string) => {
        setInternalValue(insertText);
        setValue(insertText);
        setShowSkillsGallery(false);
        setShowCommandPalette(false);
        setTimeout(() => { textareaRef.current?.focus(); adjustHeight(); }, 0);
    };

    const processFile = (file: File) => {
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const base64Data = e.target?.result as string;
                setAttachments(prev => [...prev, { name: file.name, data: base64Data, type: 'image' }]);
            };
            reader.readAsDataURL(file);
        } else {
            // Non-image external file (experimental)
            setAttachments(prev => [...prev, { name: file.name, data: '', type: 'file' }]);
        }
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        files.forEach(processFile);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    // Video YEREL dosya: Electron 34'te File.path kaldırıldı → main-process dialog
    // mutlak yolu doğrudan döndürür (base64 YOK — video büyük).
    const pickVideoFile = async () => {
        const ipc = (window as any).ipc;
        if (!ipc) return;
        const picked = await ipc.invoke('open-video-dialog');  // [{path, name}] | null
        if (picked && picked.length) {
            setAttachments(prev => [...prev, ...picked.map((v: any) => ({
                name: v.name, data: '', type: 'video' as const, path: v.path,
            }))]);
        }
    };

    const handlePaste = (e: React.ClipboardEvent) => {
        const items = Array.from(e.clipboardData.items);
        items.forEach(item => {
            if (item.type.startsWith('image/')) {
                const file = item.getAsFile();
                if (file) processFile(file);
            }
        });
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        
        // 1. Internal File Drop (from Sidebar)
        // ⚠️ `useFileSystem.ts`'teki `setData` ile BİREBİR eşleşmek zorunda; ayrışırsa
        // dosya sürükleme sessizce çalışmaz hale gelir (aynı oturum içi, sürüm riski yok).
        const internalData = e.dataTransfer.getData('application/x-gamachine-file');
        if (internalData) {
            try {
                const entry = JSON.parse(internalData);
                if (!entry.isDirectory) {
                    if (onFileDrop) onFileDrop(entry);
                    // Add as attachment immediately
                    setAttachments(prev => {
                        if (prev.some(a => a.path === entry.path)) return prev;
                        return [...prev, { name: entry.name, data: '', type: 'file', path: entry.path }];
                    });
                    return;
                }
            } catch (err) { console.error("Internal drop error:", err); }
        }

        // 2. External File Drop (from OS)
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) {
            files.forEach(processFile);
        }
    };

    // Sync internal value when parent resets to '' (after submit)
    useEffect(() => {
        if (value === '' || value !== internalValue) {
            setInternalValue(value);
        }
    }, [value]);

    // Built-in (app) komutu + backend'den gelen Claude Code slash komutları
    const commandSuggestions: CommandSuggestion[] = useMemo(() => {
        const builtin: CommandSuggestion[] = [
            { icon: <span>🧠</span>, label: 'Compact', description: 'Sohbeti özetle ve hafızaya al', prefix: '/compact' },
        ];
        const skillSet = new Set(skills || []);
        const dynamic: CommandSuggestion[] = (slashCommands || []).map(name => ({
            icon: <span>{skillSet.has(name) ? '✨' : '/'}</span>,
            label: name,
            description: '',
            prefix: '/' + name,
            isSkill: skillSet.has(name),
        }));
        return [...builtin, ...dynamic];
    }, [slashCommands, skills]);

    // Yazdıkça filtrele: '/' sonrası metin prefix/label içinde geçenler (perf için ilk 50)
    const filteredSuggestions = useMemo(() => {
        if (!internalValue.startsWith('/')) return [];
        const q = internalValue.slice(1).toLowerCase();
        const list = q
            ? commandSuggestions.filter(c =>
                c.prefix.toLowerCase().includes(q) || c.label.toLowerCase().includes(q))
            : commandSuggestions;
        return list.slice(0, 50);
    }, [internalValue, commandSuggestions]);

    useEffect(() => {
        if (internalValue.startsWith('/') && !internalValue.includes(' ') && filteredSuggestions.length > 0) {
            setShowCommandPalette(true);
            setActiveSuggestion(0);
        } else {
            setShowCommandPalette(false);
        }
    }, [internalValue, filteredSuggestions.length]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const target = event.target as Node;
            const commandButton = document.querySelector('[data-command-button]');
            if (commandPaletteRef.current && !commandPaletteRef.current.contains(target) && !commandButton?.contains(target)) {
                setShowCommandPalette(false);
            }
            const galleryButton = document.querySelector('[data-gallery-button]');
            if (galleryRef.current && !galleryRef.current.contains(target) && !galleryButton?.contains(target)) {
                setShowSkillsGallery(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (showCommandPalette) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveSuggestion(prev => prev < filteredSuggestions.length - 1 ? prev + 1 : 0);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveSuggestion(prev => prev > 0 ? prev - 1 : filteredSuggestions.length - 1);
            } else if (e.key === 'Tab' || e.key === 'Enter') {
                e.preventDefault();
                if (activeSuggestion >= 0 && filteredSuggestions[activeSuggestion]) {
                    const selectedCommand = filteredSuggestions[activeSuggestion];
                    setInternalValue(selectedCommand.prefix + ' ');
                    setShowCommandPalette(false);
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                setShowCommandPalette(false);
            }
        } else if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (internalValue.trim() || attachments.length > 0) handleSendMessage();
        }
    };

    const handleSendMessage = async () => {
        if ((internalValue.trim() || attachments.length > 0) && !isLoading) {
            const trimmed = internalValue.trim();
            if (trimmed.startsWith('/') && onCommand) {
                const handled = onCommand(trimmed);
                if (handled) {
                    setInternalValue('');
                    setValue('');
                    adjustHeight(true);
                    return;
                }
            }
            let finalMsg = internalValue;
            const images = attachments.filter(a => a.type === 'image').map(a => a.data);
            const videos = attachments
                .filter(a => a.type === 'video')
                .map((a: any) => a.url ? { kind: 'url', url: a.url, name: a.name }
                                       : (a.path ? { kind: 'path', path: a.path, name: a.name } : null))
                .filter(Boolean);
            const fileAttachments = attachments.filter(a => a.type === 'file');

            if (fileAttachments.length > 0) {
                // If there are file attachments, we need their content. 
                // Since AnimatedChatInput doesn't have IPC, home.tsx will handle the content loading 
                // via onSendMessage or we can pass the paths and let the parent handle it.
                // For now, let's just pass images and let the parent see the paths if needed.
                // But wait, the onSendMessage signature only takes (val, images).
                // I'll update it in home.tsx to handle attachments too or just append paths to finalMsg.
                const paths = fileAttachments.filter(a => a.path).map(a => `[File Attached: ${a.path}]`).join('\n');
                if (paths) finalMsg += (finalMsg ? '\n\n' : '') + paths;
            }

            onSendMessage(finalMsg, images, videos);
            setInternalValue("");
            setValue("");
            setAttachments([]);
            adjustHeight(true);
        }
    };

    return (
        <motion.div 
            className={cn("relative backdrop-blur-2xl bg-black rounded-2xl border border-white/[0.08] shadow-2xl transition-all duration-300", 
                inputFocused ? "border-white/20 shadow-white/[0.02]" : "",
                className)}
            initial={{ scale: 0.98 }}
            animate={{ scale: 1 }}
        >
            <AnimatePresence>
                {showCommandPalette && (
                    <motion.div 
                        ref={commandPaletteRef}
                        className="absolute left-4 right-4 bottom-full mb-2 backdrop-blur-xl bg-black rounded-lg z-50 shadow-lg border border-white/10 overflow-hidden"
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 5 }}
                    >
                        <div className="py-1 bg-black max-h-[280px] overflow-y-auto">
                            {filteredSuggestions.map((suggestion, index) => (
                                <div
                                    key={suggestion.prefix}
                                    className={cn(
                                        "flex items-center gap-2 px-3 py-2 text-xs transition-colors cursor-pointer",
                                        activeSuggestion === index ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/5"
                                    )}
                                    onClick={() => {
                                        setInternalValue(suggestion.prefix + ' ');
                                        setShowCommandPalette(false);
                                    }}
                                >
                                    <div className="w-5 h-5 flex items-center justify-center text-white/60">{suggestion.icon}</div>
                                    <div className="font-medium text-[11px]">{suggestion.label}</div>
                                    {suggestion.isSkill && (
                                        <span className="text-[8px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-300 border border-violet-500/20">skill</span>
                                    )}
                                    <div className="text-white/40 text-[10px] ml-auto">{suggestion.prefix}</div>
                                </div>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Skills & Komutlar galerisi (açıklamalı, aranabilir katalog) */}
            {showSkillsGallery && (
                <div ref={galleryRef}>
                    <SkillsGallery
                        meta={commandMeta}
                        skills={skills}
                        provider={galleryProvider}
                        onSelect={handleSelectCommand}
                        onClose={() => setShowSkillsGallery(false)}
                    />
                </div>
            )}

            <div className="p-3">
                <Textarea
                    ref={textareaRef}
                    value={internalValue}
                    onChange={(e) => {
                        setInternalValue(e.target.value);
                        adjustHeight();
                    }}
                    onKeyDown={handleKeyDown}
                    onPaste={handlePaste}
                    onDrop={handleDrop}
                    onDragOver={(e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = 'copy';
                    }}
                    onFocus={() => setInputFocused(true)}
                    onBlur={() => setInputFocused(false)}
                    placeholder={disabled ? disabledPlaceholder : placeholder}
                    containerClassName="w-full"
                    disabled={disabled}
                    className={cn(
                        "w-full px-3 py-2 resize-none bg-transparent border-none text-[13px] focus:outline-none min-h-[40px] custom-scrollbar",
                        disabled ? "text-orange-500/50 cursor-not-allowed italic" : "text-white/90 placeholder:text-white/20"
                    )}
                    // maxHeight (200px) aşıldığında textarea içinde mouse/trackpad ile
                    // scroll yapılabilsin diye overflow-y: auto (önceden hidden'dı → metin kilitleniyordu)
                    style={{ overflowY: "auto" }}
                    showRing={false}
                />
            </div>

            <AnimatePresence>
                {attachments.length > 0 && (
                    <div className="px-3 pb-3 flex gap-2 overflow-x-auto custom-scrollbar no-scrollbar py-2 border-t border-white/[0.03]">
                        {attachments.map((file, index) => (
                            <motion.div 
                                key={index} 
                                initial={{ opacity: 0, scale: 0.8, x: -10 }}
                                animate={{ opacity: 1, scale: 1, x: 0 }}
                                exit={{ opacity: 0, scale: 0.8 }}
                                className="relative flex-shrink-0 group"
                            >
                                {file.type === 'image' ? (
                                    <img src={file.data} alt="preview" className="w-14 h-14 object-cover rounded-lg border border-white/10 shadow-md" />
                                ) : file.type === 'video' ? (
                                    <div className="w-14 h-14 flex flex-col items-center justify-center bg-white/5 rounded-lg border border-white/10 shadow-md px-1 overflow-hidden" title={file.name}>
                                        <span className="text-lg leading-none mb-0.5">🎬</span>
                                        <span className="text-[8px] text-white/50 truncate w-full text-center">{file.url ? 'URL' : file.name}</span>
                                    </div>
                                ) : (
                                    <div className="w-14 h-14 flex flex-col items-center justify-center bg-white/5 rounded-lg border border-white/10 shadow-md px-1 overflow-hidden">
                                        <FileUp className="w-5 h-5 text-blue-400 mb-0.5" />
                                        <span className="text-[8px] text-white/50 truncate w-full text-center">{file.name}</span>
                                    </div>
                                )}
                                <button 
                                    onClick={() => setAttachments(prev => prev.filter((_, i) => i !== index))} 
                                    className="absolute -top-1.5 -right-1.5 bg-red-500/90 text-white rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity z-10 hover:bg-red-600"
                                >
                                    <XIcon className="w-3 h-3" />
                                </button>
                            </motion.div>
                        ))}
                    </div>
                )}
            </AnimatePresence>

            <div className="p-2 border-t border-white/[0.05] flex items-center justify-between gap-4 bg-white/[0.01] rounded-b-2xl">
                <div className="flex items-center gap-2">
                    <input 
                        type="file" 
                        ref={fileInputRef} 
                        onChange={handleFileChange} 
                        accept="image/*" 
                        className="hidden" 
                        multiple 
                    />
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="p-2 rounded-lg text-white/40 hover:text-white/90 hover:bg-white/5 transition-colors"
                        title="Resim Ekle"
                    >
                        <PlusIcon className="w-3.5 h-3.5" />
                    </button>
                    <button
                        type="button"
                        onClick={pickVideoFile}
                        className="p-2 rounded-lg text-white/40 hover:text-white/90 hover:bg-white/5 transition-colors text-sm leading-none"
                        title="Video Ekle (yerel dosya) — URL için linki doğrudan mesaja yapıştır"
                    >🎬</button>
                    {commandMeta.length > 0 && (
                        <button
                            type="button"
                            data-gallery-button
                            onClick={() => { setShowSkillsGallery(v => !v); setShowCommandPalette(false); }}
                            className={cn(
                                "p-2 rounded-lg transition-colors",
                                showSkillsGallery ? "text-violet-300 bg-violet-500/10" : "text-white/40 hover:text-white/90 hover:bg-white/5"
                            )}
                            title="Skills & Komutlar"
                        >
                            <Sparkles className="w-3.5 h-3.5" />
                        </button>
                    )}
                </div>
                
                {isLoading ? (
                    <button 
                        type="button" 
                        onClick={onStop} 
                        className="px-4 py-1.5 rounded-lg text-[10px] font-bold transition-all flex items-center gap-2 bg-red-500 text-white hover:bg-red-600 shadow-[0_0_15px_rgba(239,68,68,0.3)] animate-pulse"
                    >
                        <Square className="w-3 h-3 fill-current" />
                        <span>DURDUR</span>
                    </button>
                ) : (
                    <button 
                        type="button" 
                        onClick={handleSendMessage} 
                        disabled={disabled || (!internalValue.trim() && attachments.length === 0)} 
                        className={cn(
                            "px-4 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5", 
                            (internalValue.trim() || attachments.length > 0) && !disabled
                                ? "bg-white text-black hover:bg-white/90 active:scale-95 shadow-lg shadow-white/5" 
                                : "bg-white/[0.05] text-white/20"
                        )}
                    >
                        <SendIcon className="w-3 h-3" />
                        <span>Send</span>
                    </button>
                )}
            </div>
        </motion.div>
    );
}

export function ThinkingIndicator() {
    return (
        <motion.div 
            className="fixed bottom-6 right-6 backdrop-blur-2xl bg-black rounded-full px-4 py-2 shadow-lg border border-white/[0.08] z-50"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
        >
            <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-xs text-white/70">
                    <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                    <span>Thinking</span>
                    <TypingDots />
                </div>
            </div>
        </motion.div>
    );
}

export function AnimatedAIChat({ 
    onSendMessage, 
    onStop,
    isLoading 
}: { 
    onSendMessage: (val: string) => void;
    onStop?: () => void;
    isLoading: boolean;
}) {
    const [value, setValue] = useState("");
    const [inputFocused, setInputFocused] = useState(false);

    return (
        <div className="min-h-screen flex flex-col w-full items-center justify-center bg-transparent text-white p-6 relative overflow-hidden">
            <div className="absolute inset-0 w-full h-full overflow-hidden">
                <div className="absolute top-0 left-1/4 w-96 h-96 bg-violet-500/10 rounded-full filter blur-[128px] animate-pulse" />
                <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-indigo-500/10 rounded-full filter blur-[128px] animate-pulse delay-700" />
            </div>
            <div className="w-full max-w-2xl mx-auto relative">
                <div className="text-center space-y-3 mb-12">
                    <h1 className="text-3xl font-medium tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white/90 to-white/40 pb-1">
                        How can I help today?
                    </h1>
                    <p className="text-sm text-white/40">Type a command or ask a question</p>
                </div>

                <AnimatedChatInput 
                    value={value} 
                    setValue={setValue} 
                    onSendMessage={onSendMessage} 
                    onStop={onStop}
                    isLoading={isLoading} 
                />
            </div>
            <AnimatePresence>{isLoading && <ThinkingIndicator />}</AnimatePresence>
        </div>
    );
}

function TypingDots() {
    return (
        <div className="flex items-center ml-1">
            {[1, 2, 3].map((dot) => (
                <motion.div
                    key={dot}
                    className="w-1.5 h-1.5 bg-white/90 rounded-full mx-0.5"
                    initial={{ opacity: 0.3 }}
                    animate={{ 
                        opacity: [0.3, 0.9, 0.3],
                        scale: [0.85, 1.1, 0.85]
                    }}
                    transition={{
                        duration: 1.2,
                        repeat: Infinity,
                        delay: dot * 0.15,
                        ease: "easeInOut",
                    }}
                    style={{
                        boxShadow: "0 0 4px rgba(255, 255, 255, 0.3)"
                    }}
                />
            ))}
        </div>
    );
}

interface ActionButtonProps {
    icon: React.ReactNode;
    label: string;
}

function ActionButton({ icon, label }: ActionButtonProps) {
    const [isHovered, setIsHovered] = useState(false);
    
    return (
        <motion.button
            type="button"
            whileHover={{ scale: 1.05, y: -2 }}
            whileTap={{ scale: 0.97 }}
            onHoverStart={() => setIsHovered(true)}
            onHoverEnd={() => setIsHovered(false)}
            className="flex items-center gap-2 px-4 py-2 bg-neutral-900 hover:bg-neutral-800 rounded-full border border-neutral-800 text-neutral-400 hover:text-white transition-all relative overflow-hidden group"
        >
            <div className="relative z-10 flex items-center gap-2">
                {icon}
                <span className="text-xs relative z-10">{label}</span>
            </div>
            
            <AnimatePresence>
                {isHovered && (
                    <motion.div 
                        className="absolute inset-0 bg-gradient-to-r from-violet-500/10 to-indigo-500/10"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                    />
                )}
            </AnimatePresence>
            
            <motion.span 
                className="absolute bottom-0 left-0 w-full h-0.5 bg-gradient-to-r from-violet-500 to-indigo-500"
                initial={{ width: 0 }}
                whileHover={{ width: "100%" }}
                transition={{ duration: 0.3 }}
            />
        </motion.button>
    );
}

const rippleKeyframes = `
@keyframes ripple {
  0% { transform: scale(0.5); opacity: 0.6; }
  100% { transform: scale(2); opacity: 0; }
}
`;

if (typeof document !== 'undefined') {
    const style = document.createElement('style');
    style.innerHTML = rippleKeyframes;
    document.head.appendChild(style);
}


