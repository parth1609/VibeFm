export const colors = {
  // Background colors
  background: '#1a1a1a',
  surface: '#2a2a2a',
  surfaceVariant: '#3a3a3a',
  
  // Text colors
  text: '#ffffff',
  textSecondary: '#b0b0b0',
  textTertiary: '#808080',
  
  // Primary colors
  primary: '#6366f1',
  primaryVariant: '#4f46e5',
  
  // Status colors
  error: '#ef4444',
  warning: '#f59e0b',
  success: '#10b981',
  
  // Border colors
  border: '#3a3a3a',
  borderVariant: '#4a4a4a',
  
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
