import { ExportFileEntry } from "./types";


export const splitCodeIntoFiles = (codeStr: string, workspacePath: string): ExportFileEntry[] => {
  const files: ExportFileEntry[] = [];
  const targetDir = `${workspacePath}/Assets/Scripts`;
  const usingLines = codeStr.match(/^using .+;$/gm) || [];
  const usingBlock = usingLines.join('\n');
  const classRegex = /(?:(?:public|internal|abstract|sealed|static)\s+)*class\s+(\w+)/g;
  const matches = [...codeStr.matchAll(classRegex)];

  if (matches.length <= 1) {
    const classMatch = codeStr.match(/class\s+(\w+)/);
    const className = classMatch ? classMatch[1] : 'NewScript';
    return [{
      name: `${className}.cs`,
      code: codeStr,
      path: `${targetDir}/${className}.cs`,
    }];
  }

  for (let i = 0; i < matches.length; i++) {
    const startIndex = matches[i].index!;
    const className = matches[i][1];
    let endIndex = codeStr.length;
    let depth = 0;
    let foundStart = false;

    for (let j = startIndex; j < codeStr.length; j++) {
      if (codeStr[j] === '{') {
        depth++;
        foundStart = true;
      }
      if (codeStr[j] === '}') {
        depth--;
      }
      if (foundStart && depth === 0) {
        endIndex = j + 1;
        break;
      }
    }

    let actualStart = startIndex;
    const beforeClass = codeStr.substring(0, startIndex);
    const attrMatch = beforeClass.match(/(\[[\s\S]*?\]\s*)*$/);
    if (attrMatch && attrMatch[0].trim()) {
      actualStart = startIndex - attrMatch[0].length;
    }

    files.push({
      name: `${className}.cs`,
      code: `${usingBlock}\n\n${codeStr.substring(actualStart, endIndex).trim()}\n`,
      path: `${targetDir}/${className}.cs`,
    });
  }

  return files;
};

export const parseGeneratedFiles = (response: string): ExportFileEntry[] => {
  const results: Map<string, ExportFileEntry> = new Map();

  // Pattern 1: **📄 FileName.cs** or **FileName.cs** followed by a csharp block
  // Pattern 2: ### FileName.cs or ## FileName.cs followed by a csharp block
  const headerPattern =
    /(?:\*\*(?:📄\s*)?([A-Za-z0-9_.]+\.cs)\*\*|#{2,3}\s+([A-Za-z0-9_.]+\.cs))\s*\n```(?:csharp|cs)?\n([\s\S]*?)```/g;

  let match: RegExpExecArray | null;

  while ((match = headerPattern.exec(response)) !== null) {
    const name = (match[1] || match[2]).trim();
    const code = match[3].trim();
    
    // Kodun içinde path var mı kontrol et
    const lines = code.split('\n');
    let detectedPath = '';
    for (let i = 0; i < Math.min(lines.length, 5); i++) {
      const pathMatch = lines[i].match(/\/\/\s*(?:file|path|dosya):\s*([^\n\r]+)/i);
      if (pathMatch) {
        detectedPath = pathMatch[1].trim();
        break;
      }
    }

    results.set(name, { name, code, path: detectedPath });
  }

  // Fallback: extract all ```csharp blocks (header olmayanlar için)
  const blockPattern = /```(?:csharp|cs)?\n([\s\S]*?)```/g;
  const classNamePattern = /(?:public|internal|abstract|sealed|static|\s)*class\s+(\w+)/;

  while ((match = blockPattern.exec(response)) !== null) {
    const code = match[1].trim();
    
    // Eğer bu blok zaten headerPattern ile yakalanmışsa atla
    const alreadyFound = Array.from(results.values()).some(f => f.code === code);
    if (alreadyFound) continue;

    const lines = code.split('\n');
    let detectedPath = '';
    for (let i = 0; i < Math.min(lines.length, 5); i++) {
      const pathMatch = lines[i].match(/\/\/\s*(?:file|path|dosya):\s*([^\n\r]+)/i);
      if (pathMatch) {
        detectedPath = pathMatch[1].trim();
        break;
      }
    }

    if (detectedPath) {
      const name = detectedPath.split('/').pop() || 'NewScript.cs';
      results.set(name, { name, code, path: detectedPath });
    } else {
      const classMatch = code.match(classNamePattern);
      const name = classMatch ? `${classMatch[1]}.cs` : 'NewScript.cs';
      if (!results.has(name)) {
        results.set(name, { name, code, path: '' });
      }
    }
  }

  return Array.from(results.values());
};
