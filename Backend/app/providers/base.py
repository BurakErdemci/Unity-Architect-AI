import re
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*\x07)')


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


ThinkingResult = Tuple[str, Optional[str], Optional[int]]


class AIProvider(ABC):
    @abstractmethod
    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, cwd: Optional[str] = None) -> str:
        pass

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, thinking_level: str = "medium", cwd: Optional[str] = None) -> ThinkingResult:
        return self.analyze_code(prompt, max_tokens, images, cwd=cwd), None, None

    def _clean_response(self, text: str):
        if not text: return ""
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()
