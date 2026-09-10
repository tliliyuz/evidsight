import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: 'var(--es-canvas)',
        surface: 'var(--es-surface)',
        ink: {
          primary: 'var(--es-ink-primary)',
          secondary: 'var(--es-ink-secondary)',
          muted: 'var(--es-ink-muted)',
        },
        moonstone: 'var(--es-moonstone)',
        evidence: 'var(--es-spectral-cyan)',
        danger: 'var(--es-danger)',
      },
      borderRadius: {
        control: 'var(--es-radius-control)',
        panel: 'var(--es-radius-panel)',
        major: 'var(--es-radius-major)',
      },
      fontFamily: {
        sans: 'var(--es-font-sans)',
        display: 'var(--es-font-display)',
        mono: 'var(--es-font-mono)',
      },
    },
  },
  plugins: [],
} satisfies Config
