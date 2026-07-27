import fs from 'fs';
import path from 'path';
import { describe, expect, it, vi } from 'vitest';

/**
 * Bu dosyanın koruduğu arıza: `@monaco-editor/loader` yapılandırılmadığında
 * HATA VERMİYOR — sessizce gömülü cdn.jsdelivr.net varsayılanına düşüyor.
 * Yani regresyonun sahadaki belirtisi "editör açılmıyor" değil, "editör
 * açılıyor ama kodu internetten geliyor". Gözle fark edilmiyor; o yüzden teste
 * bağlandı.
 */

const RENDERER = path.resolve(__dirname, '..', 'renderer');

const collectFiles = (dir: string, out: string[] = []): string[] => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) collectFiles(full, out);
    else if (/\.tsx?$/.test(entry.name)) out.push(full);
  }
  return out;
};

describe('Monaco loader yapılandırması', () => {
  it('modül yüklenince loader.config kök-göreli yerel yolla çağrılır', async () => {
    const config = vi.fn();
    vi.doMock('@monaco-editor/react', () => ({ loader: { config } }));

    const mod = await import('../renderer/components/home/monaco-loader');

    expect(config).toHaveBeenCalledTimes(1);
    expect(config).toHaveBeenCalledWith({ paths: { vs: mod.MONACO_VS_PATH } });

    // Değerin ŞEKLİ de bağlanıyor, sadece "bir şey verilmiş olması" değil:
    //  - '/' ile başlamalı → Monaco'nun kendi AMD loader'ı yalnızca
    //    /^((http:\/\/)|(https:\/\/)|(file:\/\/)|(\/))/ eşleşenleri mutlak sayıyor;
    //    'app://…' bu regex'e uymadığı için başına baseUrl eklenirdi.
    //  - göreli olamaz → prod belgesi `app://./home` (sonda / yok), dev ise
    //    trailingSlash yüzünden `/home/`; göreli yol iki modda farklı yere düşer.
    //  - uzak olamaz → işin bütün amacı bu.
    expect(mod.MONACO_VS_PATH).toMatch(/^\/[\w./-]+$/);
    expect(mod.MONACO_VS_PATH).not.toMatch(/^https?:/);

    vi.doUnmock('@monaco-editor/react');
  });

  it('Monaco kullanan her renderer dosyası monaco-loader zincirine bağlıdır', () => {
    // Yeni bir tüketici eklenip loader import'u unutulursa, o bileşen sessizce
    // CDN'e döner. Burası o unutmayı kırmızı bir teste çeviriyor.
    const offenders = collectFiles(RENDERER)
      .filter((file) => !file.endsWith('monaco-loader.ts'))
      .filter((file) => fs.readFileSync(file, 'utf-8').includes('@monaco-editor/react'))
      .filter((file) => !/from ['"].*monaco-(loader|theme)['"]|import ['"].*monaco-loader['"]/.test(
        fs.readFileSync(file, 'utf-8')
      ));

    expect(offenders.map((f) => path.relative(RENDERER, f))).toEqual([]);
  });
});
