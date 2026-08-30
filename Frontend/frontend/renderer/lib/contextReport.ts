/**
 * `/context` çıktısının özet satırını ayrıştırır.
 *
 * `SlashCommandCard` içinde yaşıyordu; gösterge de aynı sayıya ihtiyaç
 * duyunca ortak eve taşındı. İkinci bir kopya, aynı çıktının iki ayrı
 * yorumunu doğururdu — kart bir sayı gösterirken göstergenin başka bir sayı
 * göstermesi, ve ikisinin neden ayrıştığının hiç fark edilmemesi.
 */

export interface ContextReport {
  /** Ham biçimiyle kullanılan miktar, ör. "69.9k". */
  used: string;
  /** Ham biçimiyle pencere, ör. "1m". */
  total: string;
  pct: number;
  model?: string;
}

export function parseContextReport(text: string): ContextReport | null {
  const m = text.match(
    /\*\*Tokens:\*\*\s*([\d.]+\s*[kKmMbB]?)\s*\/\s*([\d.]+\s*[kKmMbB]?)\s*\((\d+(?:\.\d+)?)%\)/,
  );
  if (!m) return null;
  const model = text.match(/\*\*Model:\*\*\s*([^\n*]+)/);
  return {
    used: m[1].replace(/\s+/g, ''),
    total: m[2].replace(/\s+/g, ''),
    pct: Math.min(100, parseFloat(m[3])),
    model: model?.[1]?.trim(),
  };
}
