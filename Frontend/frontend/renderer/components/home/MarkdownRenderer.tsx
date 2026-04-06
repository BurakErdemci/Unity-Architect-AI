import { useState } from "react";
import { Check, Copy, FileDown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/cjs/styles/prism";


export const MarkdownRenderer = ({
  content,
  workspacePath,
  onExportToUnity,
}: {
  content: string;
  workspacePath?: string | null;
  onExportToUnity?: (code: string) => void;
}) => {
  const [copiedBlock, setCopiedBlock] = useState<string | null>(null);

  const handleCopy = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedBlock(code);
    setTimeout(() => setCopiedBlock(null), 2000);
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ inline, className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || "");
          const codeString = String(children).replace(/\n$/, "");

          return !inline && match ? (
            <div className="relative group my-4">
              <div className="absolute top-2 right-2 z-10 flex items-center gap-1.5">
                <span className="text-[10px] text-slate-500 font-mono uppercase">{match[1]}</span>
                {match[1] === "csharp" && workspacePath && onExportToUnity && (
                  <button
                    onClick={() => onExportToUnity(codeString)}
                    className="p-1.5 rounded-md bg-emerald-900/80 hover:bg-emerald-700 border border-emerald-700/50 text-emerald-400 hover:text-emerald-200 transition-all opacity-0 group-hover:opacity-100"
                    title="Unity Projesine Aktar"
                  >
                    <FileDown size={13} />
                  </button>
                )}
                <button
                  onClick={() => handleCopy(codeString)}
                  className="p-1.5 rounded-md bg-slate-800/80 hover:bg-slate-700 border border-slate-700/50 text-slate-400 hover:text-slate-200 transition-all opacity-0 group-hover:opacity-100"
                  title="Kopyala"
                >
                  {copiedBlock === codeString ? (
                    <Check size={13} className="text-emerald-400" />
                  ) : (
                    <Copy size={13} />
                  )}
                </button>
              </div>
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={match[1]}
                PreTag="div"
                className="rounded-xl !bg-[#0a0c10] border border-slate-800 shadow-lg !pt-10 max-h-[500px] overflow-y-auto custom-scrollbar"
                {...props}
              >
                {codeString}
              </SyntaxHighlighter>
            </div>
          ) : (
            <code className="bg-blue-500/10 px-1.5 py-0.5 rounded text-blue-400 font-mono text-xs font-semibold" {...props}>
              {children}
            </code>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
};
