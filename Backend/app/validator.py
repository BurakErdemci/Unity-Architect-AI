import re
from typing import List, Tuple

class ResponseValidator:
    """AI çıktısını denetleyen ve düzeltme talep eden katman."""
    
    @staticmethod
    def validate(response: str) -> Tuple[bool, List[str]]:
        issues = []
        
        # 1. Kod bloğu var mı?
        if "```csharp" not in response:
            issues.append("Kod bloğu (```csharp) eksik.")
        
        # 2. Tembellik kontrolü (AI kodu yarım mı bıraktı?)
        if "..." in response or "// .." in response:
            issues.append("Kod yarım bırakılmış (... kullanılmış). Lütfen tam kodu yaz.")

        # 3. Kritik Unity Hatası: FixedUpdate içinde Input kalmış mı?
        code_blocks = re.findall(r'```csharp(.*?)```', response, re.DOTALL)
        for block in code_blocks:
            if "void FixedUpdate" in block and "Input." in block:
                issues.append("HATA: FixedUpdate içinde hala Input tespiti var. Bunu Update'e taşı!")

        return (len(issues) == 0, issues)