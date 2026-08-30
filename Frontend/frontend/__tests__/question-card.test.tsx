/**
 * Soru kartının SÖZLEŞMESİ — çoklu seçim, serbest metin, atlama.
 *
 * Neden bu testler var: kartın karşılığı olan araç (AskUserQuestion) modele
 * şunu söylüyor — ölçüldü 30 Ağu 2026, SDK'nın paketlediği `claude.exe`'nin
 * içindeki metinlerden:
 *
 *   "AskUserQuestion always includes a Skip button and a free-text input box
 *    for custom answers, so do not include `None` or `Other` as options."
 *   "The answers provided by the user (question text -> answer string;
 *    multi-select answers are comma-separated)"
 *
 * Yani model, arayüzün bir çıkış yolu sunduğuna GÜVENEREK "hiçbiri" seçeneği
 * koymuyor. Kart 30 Ağu 2026'ya kadar ne atlama ne serbest metin sunuyordu;
 * seçeneklerin hiçbirine katılmayan kullanıcının tek çıkışı turu öldürmekti.
 *
 * Testler bu yüzden görünüşe değil GÖNDERİLEN YÜKE bakıyor: kullanıcının
 * gördüğü ile modele giden şey aynı mı. `multiSelect` alanı bir yıl boyunca
 * tanımlıydı ve hiç okunmuyordu — bir alanın var olması onu ölçmüyor.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import React from 'react'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

import { QuestionApproval } from '../renderer/components/home/QuestionApproval'

afterEach(() => cleanup())

const TEK = [{
  question: 'Hangi kütüphane?',
  options: [{ label: 'zod' }, { label: 'yup' }],
}]

const COKLU = [{
  question: 'Hangi özellikler açılsın?',
  multiSelect: true,
  options: [{ label: 'auth' }, { label: 'cache' }, { label: 'log' }],
}]

const kartiCiz = (questions: any[]) => {
  const onSubmit = vi.fn()
  render(<QuestionApproval questions={questions} onSubmit={onSubmit} />)
  return onSubmit
}

const secenekler = () => screen.getAllByTestId('question-option')
const gonder = () => screen.getByTestId('question-send') as HTMLButtonElement
const serbestMetin = (i = 0) => screen.getAllByTestId('question-custom')[i]
const atla = (i = 0) => screen.getAllByTestId('question-skip')[i]

describe('çoklu seçim', () => {
  it('iki seçenek birden seçilebiliyor ve virgülle birleşiyor', () => {
    const onSubmit = kartiCiz(COKLU)
    fireEvent.click(secenekler()[0])
    fireEvent.click(secenekler()[2])
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangi özellikler açılsın?': 'auth, log' })
  })

  it('aynı seçeneğe ikinci tık onu geri çıkarıyor', () => {
    const onSubmit = kartiCiz(COKLU)
    fireEvent.click(secenekler()[0])
    fireEvent.click(secenekler()[1])
    fireEvent.click(secenekler()[0])
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangi özellikler açılsın?': 'cache' })
  })

  it('tek seçimli soruda ikinci tık öncekini DEĞİŞTİRİYOR, eklemiyor', () => {
    const onSubmit = kartiCiz(TEK)
    fireEvent.click(secenekler()[0])
    fireEvent.click(secenekler()[1])
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangi kütüphane?': 'yup' })
  })
})

describe('serbest metin', () => {
  it('hiç seçenek seçmeden yalnız yazarak cevaplanabiliyor', () => {
    const onSubmit = kartiCiz(TEK)
    expect(gonder().disabled).toBe(true)
    fireEvent.change(serbestMetin(), { target: { value: 'valibot' } })
    expect(gonder().disabled).toBe(false)
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangi kütüphane?': 'valibot' })
  })

  it('yalnız boşluk yazmak cevap SAYILMIYOR', () => {
    kartiCiz(TEK)
    fireEvent.change(serbestMetin(), { target: { value: '   ' } })
    expect(gonder().disabled).toBe(true)
  })

  it('çoklu seçimde yazılan metin seçilenlere EKLENİYOR', () => {
    const onSubmit = kartiCiz(COKLU)
    fireEvent.click(secenekler()[1])
    fireEvent.change(serbestMetin(), { target: { value: 'metrics' } })
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangi özellikler açılsın?': 'cache, metrics' })
  })

  it('tek seçimde yazmak seçili seçeneği TEMİZLİYOR — ikisi çelişemez', () => {
    const onSubmit = kartiCiz(TEK)
    fireEvent.click(secenekler()[0])
    fireEvent.change(serbestMetin(), { target: { value: 'valibot' } })
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangi kütüphane?': 'valibot' })
  })
})

describe('atlama', () => {
  it('atlanan soru yükte HİÇ GÖRÜNMÜYOR — boş metin olarak değil', () => {
    const onSubmit = kartiCiz(TEK)
    fireEvent.click(atla())
    expect(gonder().disabled).toBe(false)
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({})
  })

  it('atlama geri alınabiliyor ve soru yeniden cevap bekliyor', () => {
    kartiCiz(TEK)
    fireEvent.click(atla())
    expect(gonder().disabled).toBe(false)
    fireEvent.click(atla())
    expect(gonder().disabled).toBe(true)
  })

  // Atlanan soru gerçekten donuk: seçenekler ve metin kutusu devre dışı, o
  // yüzden bir tık atlamayı SESSİZCE geri alamıyor. Bu test önce onu
  // sabitliyor, sonra geri almanın tek yolunun atlama düğmesi olduğunu.
  it('atlanmışken seçenekler ve metin kutusu devre dışı', () => {
    kartiCiz(TEK)
    fireEvent.click(atla())
    expect((secenekler()[0] as HTMLButtonElement).disabled).toBe(true)
    expect((serbestMetin() as HTMLInputElement).disabled).toBe(true)
  })

  it('geri alındıktan sonra seçim yeniden çalışıyor', () => {
    const onSubmit = kartiCiz(TEK)
    fireEvent.click(atla())
    fireEvent.click(atla())
    fireEvent.click(secenekler()[0])
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangi kütüphane?': 'zod' })
  })
})

describe('birden fazla soru', () => {
  const IKI = [
    { question: 'Birinci?', options: [{ label: 'a' }, { label: 'b' }] },
    { question: 'İkinci?', options: [{ label: 'c' }, { label: 'd' }] },
  ]

  it('hepsi çözülmeden gönderilemiyor, biri atlanınca çözülmüş sayılıyor', () => {
    const onSubmit = kartiCiz(IKI)
    expect(gonder().disabled).toBe(true)
    fireEvent.click(secenekler()[0])          // Birinci? → a
    expect(gonder().disabled).toBe(true)      // İkinci hâlâ açık
    fireEvent.click(atla(1))
    expect(gonder().disabled).toBe(false)
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Birinci?': 'a' })
  })
})

describe('model metni temizliği', () => {
  // U+202E metni ters çeviriyor: kullanıcının gördüğü etiket ile gönderilen
  // dizenin ayrışabildiği yer burası. Gösterim temizlenip değer ham gönderilse
  // kapı tek dala konmuş olurdu — bu test iki ucu birden sabitliyor.
  const SINSI = [{
    question: 'Hangisi?',
    options: [{ label: 'gu' + '\u202E' + 'venli' }, { label: 'digeri' }],
  }]

  it('etiketteki yön değiştirici hem ekrandan hem gönderilen cevaptan siliniyor', () => {
    const onSubmit = kartiCiz(SINSI)
    expect(screen.queryByText('gu' + '\u202E' + 'venli')).toBeNull()
    expect(screen.getByText('guvenli')).toBeTruthy()
    fireEvent.click(secenekler()[0])
    fireEvent.click(gonder())
    expect(onSubmit).toHaveBeenCalledWith({ 'Hangisi?': 'guvenli' })
  })
})
