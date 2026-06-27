import React from 'react'
import type { AppProps } from 'next/app'

import '../styles/globals.css'
import { ConfirmDialogHost } from '../components/ui/ConfirmDialog'

function MyApp({ Component, pageProps }: AppProps) {
  return (
    <>
      <Component {...pageProps} />
      {/* Native confirm() yerine uygulama-içi onay (Electron focus-kilit bug fix) */}
      <ConfirmDialogHost />
    </>
  )
}

export default MyApp
