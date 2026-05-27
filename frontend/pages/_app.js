import '../styles/globals.css'
import { Fraunces, IBM_Plex_Sans } from 'next/font/google'

const displayFont = Fraunces({
  subsets: ['latin'],
  weight: ['500', '600', '700'],
  variable: '--font-display',
})

const bodyFont = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-body',
})

export default function App({ Component, pageProps }) {
  return (
    <div className={`${bodyFont.className} ${displayFont.variable} app-theme`}>
      <Component {...pageProps} />
    </div>
  )
}
