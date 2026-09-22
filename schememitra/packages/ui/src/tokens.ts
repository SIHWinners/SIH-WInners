/**
 * Design tokens — single source for web (CSS variables via tokens.css) and React Native
 * (imported directly). Values follow the SchemeMitra design system (spec §7).
 * `*Ink` colours are text-safe variants of status/accent colours that are too light for
 * body text on white (ADR-011); the base colours stay for fills, borders and icons.
 */
export const colors = {
  light: {
    brand: '#0B3D91',
    brandInk: '#082B66',
    brandTint: '#E8EEF9',
    onBrand: '#FFFFFF',
    accent: '#E07A1F',
    accentInk: '#9A4A0A',
    accentTint: '#FDF0E4',
    success: '#1B7F4B',
    successInk: '#14633A',
    successTint: '#E6F4EC',
    warning: '#B7791F',
    warningInk: '#8A5A12',
    warningTint: '#FDF3E1',
    danger: '#B42318',
    dangerInk: '#9A1D13',
    dangerTint: '#FDECEA',
    bg: '#F7F8FB',
    surface: '#FFFFFF',
    surfaceAlt: '#F0F2F7',
    border: '#E3E7EF',
    borderStrong: '#7A8699',
    text: '#101828',
    muted: '#475467',
    focus: '#0B3D91',
  },
  dark: {
    brand: '#7FA8FF',
    brandInk: '#C9D8FF',
    brandTint: '#1A2A4A',
    onBrand: '#0B1220',
    accent: '#F5A25D',
    accentInk: '#F5A25D',
    accentTint: '#3A2615',
    success: '#4CC38A',
    successInk: '#4CC38A',
    successTint: '#12301F',
    warning: '#E6B35A',
    warningInk: '#E6B35A',
    warningTint: '#33270F',
    danger: '#F97066',
    dangerInk: '#F97066',
    dangerTint: '#3A1614',
    bg: '#0B1220',
    surface: '#121A2B',
    surfaceAlt: '#18223A',
    border: '#24304A',
    borderStrong: '#5B6B8C',
    text: '#E6EAF2',
    muted: '#98A2B3',
    focus: '#7FA8FF',
  },
} as const;

export type ColorScheme = keyof typeof colors;
export type ColorToken = keyof (typeof colors)['light'];

export const fontScale = [12, 14, 16, 18, 22, 28, 36] as const;
export const lineHeight = { latin: 1.4, indic: 1.5 } as const;
export const radii = { sm: 6, md: 10, lg: 16, pill: 999 } as const;
export const space = [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64] as const;
export const touchTarget = 48;
export const motionMs = { fast: 120, base: 180, max: 200 } as const;

/** Noto families per script. Web loads only the active script's subset. */
export const scriptFonts = {
  Latn: 'Noto Sans',
  Deva: 'Noto Sans Devanagari',
  Beng: 'Noto Sans Bengali',
  Gujr: 'Noto Sans Gujarati',
  Guru: 'Noto Sans Gurmukhi',
  Taml: 'Noto Sans Tamil',
  Telu: 'Noto Sans Telugu',
  Knda: 'Noto Sans Kannada',
  Mlym: 'Noto Sans Malayalam',
  Orya: 'Noto Sans Oriya',
  Arab: 'Noto Naskh Arabic',
} as const;

/**
 * Pairs that must meet WCAG 2.2 AA. `text` pairs need 4.5:1, `ui` pairs (icons, borders,
 * focus rings, large fills with no text) need 3:1. Checked in CI by scripts/check-contrast.mjs.
 */
export const contrastPairs: Array<{ fg: ColorToken; bg: ColorToken; kind: 'text' | 'ui' }> = [
  { fg: 'text', bg: 'bg', kind: 'text' },
  { fg: 'text', bg: 'surface', kind: 'text' },
  { fg: 'text', bg: 'surfaceAlt', kind: 'text' },
  { fg: 'muted', bg: 'bg', kind: 'text' },
  { fg: 'muted', bg: 'surface', kind: 'text' },
  { fg: 'brand', bg: 'surface', kind: 'text' },
  { fg: 'brand', bg: 'bg', kind: 'text' },
  { fg: 'brandInk', bg: 'brandTint', kind: 'text' },
  { fg: 'onBrand', bg: 'brand', kind: 'text' },
  { fg: 'accentInk', bg: 'surface', kind: 'text' },
  { fg: 'accentInk', bg: 'accentTint', kind: 'text' },
  { fg: 'successInk', bg: 'surface', kind: 'text' },
  { fg: 'successInk', bg: 'successTint', kind: 'text' },
  { fg: 'warningInk', bg: 'surface', kind: 'text' },
  { fg: 'warningInk', bg: 'warningTint', kind: 'text' },
  { fg: 'dangerInk', bg: 'surface', kind: 'text' },
  { fg: 'dangerInk', bg: 'dangerTint', kind: 'text' },
  { fg: 'accent', bg: 'surface', kind: 'ui' },
  { fg: 'warning', bg: 'surface', kind: 'ui' },
  { fg: 'success', bg: 'surface', kind: 'ui' },
  { fg: 'danger', bg: 'surface', kind: 'ui' },
  { fg: 'borderStrong', bg: 'surface', kind: 'ui' },
  { fg: 'focus', bg: 'bg', kind: 'ui' },
];
