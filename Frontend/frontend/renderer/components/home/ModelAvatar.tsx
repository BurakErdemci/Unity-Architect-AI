import { ModelLogo } from "../ui/ModelLogos";


export const ModelAvatar = ({
  provider,
  size = 13,
  containerSize = "h-6 w-6",
  className = "",
}: {
  provider?: string;
  size?: number;
  containerSize?: string;
  className?: string;
}) => {
  const normalizedProvider = provider?.toLowerCase() || "";
  let bg = "bg-gradient-to-br from-blue-500 to-violet-500";
  let iconColor = "text-white";

  if (normalizedProvider.includes("copilot") || normalizedProvider.includes("github")) {
    bg = "bg-[#24292F] border border-white/15";
  } else if (normalizedProvider.includes("cursor")) {
    bg = "bg-black border border-white/20";
  } else if (normalizedProvider.includes("opencode")) {
    bg = "bg-gradient-to-br from-[#0F766E] to-[#134E4A]";
  } else if (normalizedProvider.includes("anthropic") || normalizedProvider.includes("claude")) {
    bg = "bg-[#D97757]";
  } else if (normalizedProvider.includes("openai")) {
    bg = "bg-gradient-to-br from-[#10A37F] to-[#0A6B53]";
  } else if (normalizedProvider.includes("google") || normalizedProvider.includes("gemini")) {
    bg = "bg-white";
    iconColor = "text-[#4285F4]";
  } else if (normalizedProvider.includes("deepseek")) {
    bg = "bg-gradient-to-br from-[#3B82F6] to-[#1E3A8A]";
  } else if (normalizedProvider.includes("moonshot") || normalizedProvider.includes("openrouter")) {
    bg = "bg-gradient-to-br from-[#7C3AED] to-[#4C1D95]";
  } else if (normalizedProvider.includes("z-ai") || normalizedProvider.includes("glm") || normalizedProvider.includes("zhipu")) {
    bg = "bg-gradient-to-br from-[#14B8A6] to-[#0F766E]";
  } else if (normalizedProvider.includes("groq")) {
    bg = "bg-gradient-to-br from-[#F55036] to-[#D33C25]";
  } else if (normalizedProvider.includes("ollama")) {
    bg = "bg-slate-900";
  }

  return (
    <div className={`${containerSize} ${bg} rounded-md flex items-center justify-center shrink-0 ${className} shadow-sm overflow-hidden`}>
      <ModelLogo provider={provider} size={size} className={iconColor} />
    </div>
  );
};
