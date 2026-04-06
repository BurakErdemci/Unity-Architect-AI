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
