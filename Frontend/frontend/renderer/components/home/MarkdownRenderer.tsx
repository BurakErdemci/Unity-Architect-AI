import { memo, useState } from "react";
import { Check, Copy, FileDown, Eye, EyeOff, FileCode } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/cjs/styles/prism";

const CodeBlock = ({ match, codeString, workspacePath, onExportToUnity, handleCopy, copiedBlock }: any) => {
  const isAgentFile = codeString.trim().startsWith("// path:");
  const [isCollapsed, setIsCollapsed] = useState(isAgentFile); // Ajan dosyaları varsayılan kapalı

  let fileName = "";
  let filePath = "";
  if (isAgentFile) {
    const firstLine = codeString.split('\n')[0];
    filePath = firstLine.replace("// path:", "").trim();
    fileName = filePath.split('/').pop() || "Script.cs";
  }

  return (
    <div className="relative group my-4">
      {isAgentFile ? (
        <div className={`rounded-xl border transition-all ${isCollapsed ? 'border-slate-800 bg-[#0d1117] hover:border-blue-500/30' : 'border-slate-800 bg-transparent'}`}>
          <div className="flex items-center justify-between px-4 py-2.5 bg-[#0a0c10] rounded-t-xl border-b border-slate-800/50">
            <div className="flex items-center gap-2.5">
              <FileCode size={14} className="text-blue-400" />
              <div className="flex flex-col">
                <span className="text-[11px] font-bold text-slate-200 leading-none">{fileName}</span>
                <span className="text-[9px] text-slate-500 font-mono mt-1">{filePath}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsCollapsed(!isCollapsed)}
                className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-all text-[10px] font-semibold"
              >
                {isCollapsed ? <><Eye size={12} /> Kodu Göster</> : <><EyeOff size={12} /> Gizle</>}
              </button>
              {!isCollapsed && (
                <button
                  onClick={() => handleCopy(codeString)}
                  className="p-1.5 rounded-md bg-slate-800/80 hover:bg-slate-700 border border-slate-700/50 text-slate-400 hover:text-slate-200 transition-all"
                  title="Kopyala"
                >
                  {copiedBlock === codeString ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                </button>
              )}
            </div>
          </div>
          
          {!isCollapsed && (
            <SyntaxHighlighter
              style={vscDarkPlus}
              language={match[1]}
              PreTag="div"
              className="!bg-[#0a0c10] !m-0 !rounded-b-xl border-none max-h-[500px] overflow-y-auto custom-scrollbar text-[12px]"
            >
              {codeString}
            </SyntaxHighlighter>
          )}
        </div>
      ) : (
        <>
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
              {copiedBlock === codeString ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            </button>
          </div>
          <SyntaxHighlighter
            style={vscDarkPlus}
            language={match[1]}
            PreTag="div"
            className="rounded-xl !bg-[#0a0c10] border border-slate-800 shadow-lg !pt-10 max-h-[500px] overflow-y-auto custom-scrollbar"
          >
            {codeString}
          </SyntaxHighlighter>
        </>
      )}
    </div>
  );
};

const MarkdownRendererInner = ({
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
        // Tablo panelden taşmasın: kendi kartında yatay scroll (bkz. globals.css .chat-table)
        table({ children, ...props }: any) {
          return (
            <div className="chat-table custom-scrollbar">
              <table {...props}>{children}</table>
            </div>
          );
        },
        code({ inline, className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || "");
          const codeString = String(children).replace(/\n$/, "");

          return !inline && match ? (
            <CodeBlock 
              match={match} 
              codeString={codeString} 
              workspacePath={workspacePath} 
              onExportToUnity={onExportToUnity}
              handleCopy={handleCopy}
              copiedBlock={copiedBlock}
              {...props}
            />
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

export const MarkdownRenderer = memo(MarkdownRendererInner);
