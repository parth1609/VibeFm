export const colors = {
  // Background colors
  background: '#08080C',
  surface: '#13131C',
  surfaceVariant: '#1C1C28',
  surfaceElevated: '#262633',

  // Text colors
  text: '#ffffff',
  textSecondary: '#A5A5B8',
  textTertiary: '#6E6E82',

  // Primary colors
  primary: '#8B5CF6',
  primaryVariant: '#7C3AED',
  primarySoft: 'rgba(139, 92, 246, 0.16)',
  accent: '#22D3EE',

  // Status colors
  live: '#F43F5E',
  error: '#F87171',
  warning: '#FBBF24',
  success: '#34D399',

  // Border colors
  border: '#242433',
  borderVariant: '#33334A',

  // Overlay colors
  overlay: 'rgba(0, 0, 0, 0.5)',
  overlayLight: 'rgba(0, 0, 0, 0.3)',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const borderRadius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  xxl: 24,
  full: 9999,
};

export const typography = {
  title: {
    fontSize: 32,
    fontWeight: 'bold' as const,
  },
  heading: {
    fontSize: 24,
    fontWeight: 'bold' as const,
  },
  subheading: {
    fontSize: 20,
    fontWeight: '600' as const,
  },
  body: {
    fontSize: 16,
    fontWeight: 'normal' as const,
  },
  caption: {
    fontSize: 14,
    fontWeight: 'normal' as const,
  },
  small: {
    fontSize: 12,
    fontWeight: 'normal' as const,
  },
};
