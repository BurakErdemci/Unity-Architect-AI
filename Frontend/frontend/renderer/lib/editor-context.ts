/**
 * Diskte zaten bulunan dosyayı her sohbette tekrar modele göndermeyiz; ajan
 * gerektiğinde workspace araçlarıyla okuyabilir. Yalnızca henüz kaydedilmemiş
 * editör değişiklikleri araçlardan görünmeyeceği için prompt bağlamına eklenir.
 */
export function getUnsavedEditorContext(code: string, isDirty: boolean): string {
  return isDirty ? code : '';
}
