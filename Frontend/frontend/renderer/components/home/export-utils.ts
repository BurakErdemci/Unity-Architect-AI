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
  let foundHeaders = false;

  while ((match = headerPattern.exec(response)) !== null) {
    foundHeaders = true;
    const name = (match[1] || match[2]).trim();
    const code = match[3].trim();
    results.set(name, { name, code, path: '' });
  }

  if (foundHeaders) {
    return Array.from(results.values());
  }

  // Fallback: extract all ```csharp blocks and detect class name from inside
  const blockPattern = /```(?:csharp|cs)?\n([\s\S]*?)```/g;
  const classNamePattern = /(?:public|internal|abstract|sealed|static|\s)*class\s+(\w+)/;

  while ((match = blockPattern.exec(response)) !== null) {
    const code = match[1].trim();
    const classMatch = code.match(classNamePattern);
    const name = classMatch ? `${classMatch[1]}.cs` : 'NewScript.cs';
    // keep last occurrence — overwrite any previous entry with the same name
    results.set(name, { name, code, path: '' });
  }

  return Array.from(results.values());
};
