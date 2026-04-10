"use client";

import { useEffect, useRef, useCallback, useTransition } from "react";
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
    LoaderIcon,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import * as React from "react"

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
    isLoading,
    placeholder = "Ask zap a question...",
    className,
    includeEditorCode = false,
    onToggleIncludeCode
}: { 
    value: string;
    setValue: (val: string) => void;
    onSendMessage: (val: string) => void;
    isLoading: boolean;
    placeholder?: string;
    className?: string;
    includeEditorCode?: boolean;
    onToggleIncludeCode?: () => void;
}) {
    // Typing state is INTERNAL — does not propagate to parent on every keystroke.
    // This prevents home.tsx (with its large message list) from re-rendering while the user types.
    const [internalValue, setInternalValue] = useState(value);
    const [attachments, setAttachments] = useState<string[]>([]);
    const [activeSuggestion, setActiveSuggestion] = useState<number>(-1);
    const [showCommandPalette, setShowCommandPalette] = useState(false);
    const { textareaRef, adjustHeight } = useAutoResizeTextarea({
        minHeight: 60,
        maxHeight: 200,
    });
    const [inputFocused, setInputFocused] = useState(false);
    const commandPaletteRef = useRef<HTMLDivElement>(null);

    // Sync internal value when parent resets to '' (after submit) or sets a prefix command
    useEffect(() => {
        if (value === '' || value !== internalValue) {
            setInternalValue(value);
        }
    }, [value]);

    const commandSuggestions: CommandSuggestion[] = [];

    useEffect(() => {
        if (internalValue.startsWith('/') && !internalValue.includes(' ')) {
            setShowCommandPalette(true);
            const matchingSuggestionIndex = commandSuggestions.findIndex(cmd => cmd.prefix.startsWith(internalValue));
            setActiveSuggestion(matchingSuggestionIndex);
        } else {
            setShowCommandPalette(false);
        }
    }, [internalValue]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const target = event.target as Node;
            const commandButton = document.querySelector('[data-command-button]');
            if (commandPaletteRef.current && !commandPaletteRef.current.contains(target) && !commandButton?.contains(target)) {
                setShowCommandPalette(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (showCommandPalette) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveSuggestion(prev => prev < commandSuggestions.length - 1 ? prev + 1 : 0);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveSuggestion(prev => prev > 0 ? prev - 1 : commandSuggestions.length - 1);
            } else if (e.key === 'Tab' || e.key === 'Enter') {
                e.preventDefault();
                if (activeSuggestion >= 0) {
                    const selectedCommand = commandSuggestions[activeSuggestion];
                    setInternalValue(selectedCommand.prefix + ' ');
                    setShowCommandPalette(false);
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                setShowCommandPalette(false);
            }
        } else if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (internalValue.trim()) handleSendMessage();
        }
    };

    const handleSendMessage = () => {
        if (internalValue.trim() && !isLoading) {
            onSendMessage(internalValue);
            setInternalValue("");
            setValue("");
            adjustHeight(true);
        }
    };

    return (
        <motion.div 
            className={cn("relative backdrop-blur-2xl bg-black rounded-2xl border border-white/[0.08] shadow-2xl", className)}
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
                        <div className="py-1 bg-black">
                            {commandSuggestions.map((suggestion, index) => (
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
                                    <div className="text-white/40 text-[10px] ml-1">{suggestion.prefix}</div>
                                </div>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="p-3">
                <Textarea
                    ref={textareaRef}
                    value={internalValue}
                    onChange={(e) => {
                        setInternalValue(e.target.value);
                        adjustHeight();
                    }}
                    onKeyDown={handleKeyDown}
                    onFocus={() => setInputFocused(true)}
                    onBlur={() => setInputFocused(false)}
                    placeholder={placeholder}
                    containerClassName="w-full"
                    className="w-full px-3 py-2 resize-none bg-transparent border-none text-white/90 text-[13px] focus:outline-none placeholder:text-white/20 min-h-[40px]"
                    style={{ overflow: "hidden" }}
                    showRing={false}
                />
            </div>

            <AnimatePresence>
                {attachments.length > 0 && (
                    <div className="px-3 pb-3 flex gap-2 flex-wrap">
                        {attachments.map((file, index) => (
                            <div key={index} className="flex items-center gap-2 text-[10px] bg-white/[0.03] py-1 px-2 rounded-md text-white/70 border border-white/5">
                                <span>{file}</span>
                                <button onClick={() => setAttachments(prev => prev.filter((_, i) => i !== index))} className="text-white/40 hover:text-white transition-colors">
                                    <XIcon className="w-3 h-3" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </AnimatePresence>

            <div className="p-2 border-t border-white/[0.05] flex items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                    <button 
                        type="button" 
                        onClick={() => onToggleIncludeCode && onToggleIncludeCode()} 
                        className={cn("p-2 rounded-lg transition-colors flex items-center gap-1.5 border", includeEditorCode ? "bg-blue-600/20 text-blue-400 border-blue-500/30" : "text-white/40 hover:text-white/90 border-transparent hover:bg-white/5")}
                        title="Kod Editöründeki İçeriği Sohbete Ekle"
                    >
                        <Paperclip className="w-3.5 h-3.5" />
                        {includeEditorCode && <span className="text-[10px] font-semibold tracking-wider">KOD EKLENİYOR</span>}
                    </button>

                </div>
                
                <button type="button" onClick={handleSendMessage} disabled={isLoading || !internalValue.trim()} className={cn("px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5", internalValue.trim() ? "bg-white text-[#0A0A0B]" : "bg-white/[0.05] text-white/40")}>
                    {isLoading ? <LoaderIcon className="w-3 h-3 animate-spin" /> : <SendIcon className="w-3 h-3" />}
                    <span>Send</span>
                </button>
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
    isLoading 
}: { 
    onSendMessage: (val: string) => void;
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


