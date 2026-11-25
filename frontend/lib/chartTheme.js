// Felles innstillinger for recharts.

// Standardanimasjonen (1500 ms, 'ease') føles treg; dette gir en kortere,
// mykere inngang. Slås av for brukere som har bedt om redusert bevegelse.
const reducedMotion = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export const CHART_ANIM = {
  animationDuration: 600,
  animationEasing: 'ease-out',
  isAnimationActive: !reducedMotion,
}

// Y-akse for priser over tid: starter rett under laveste pris i stedet for
// på 0, slik at endringer på noen få kroner faktisk synes i grafen.
export const PRICE_DOMAIN = [
  min => Math.max(0, Math.floor(min * 0.95)),
  max => Math.ceil(max * 1.03),
]
