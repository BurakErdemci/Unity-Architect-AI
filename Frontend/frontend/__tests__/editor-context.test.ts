import { describe, expect, it } from 'vitest';
import { getUnsavedEditorContext } from '../renderer/lib/editor-context';

describe('getUnsavedEditorContext', () => {
  it('kayıtlı açık dosyayı prompta tekrar eklemez', () => {
    expect(getUnsavedEditorContext('# AGENTS.md\nçok uzun proje kuralları', false)).toBe('');
  });

  it('kaydedilmemiş editör değişikliklerini aynen korur', () => {
    const code = 'public class PlayerController {\n  // henüz kaydedilmedi\n}\n';
    expect(getUnsavedEditorContext(code, true)).toBe(code);
  });

  it('boş kaydedilmemiş buffer için boş bağlam döndürür', () => {
    expect(getUnsavedEditorContext('', true)).toBe('');
  });
});
