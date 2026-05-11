import { Dimensions, PixelRatio } from 'react-native';

const { width: screenWidth, height: screenHeight } = Dimensions.get('window');

// Base dimensions (iPhone 12 dimensions as reference)
const baseWidth = 390;
const baseHeight = 844;

// Scale factor based on screen width
const scaleFactor = Math.min(screenWidth / baseWidth, screenHeight / baseHeight);

// Responsive font size function
export const responsiveFontSize = (size: number): number => {
  const newSize = size * scaleFactor;
  return Math.round(PixelRatio.roundToNearestPixel(newSize));
};

// Responsive width function
export const responsiveWidth = (width: number): number => {
  return Math.round(PixelRatio.roundToNearestPixel(width * scaleFactor));
};

// Responsive height function
export const responsiveHeight = (height: number): number => {
  return Math.round(PixelRatio.roundToNearestPixel(height * scaleFactor));
};

// Responsive padding/margin function
export const responsiveSpacing = (spacing: number): number => {
  return Math.round(PixelRatio.roundToNearestPixel(spacing * scaleFactor));
};

// Check if device is tablet
export const isTablet = (): boolean => {
  const aspectRatio = screenHeight / screenWidth;
  return aspectRatio < 1.6; // Tablets typically have aspect ratio less than 1.6
};

// Get screen orientation
export const getOrientation = (): 'portrait' | 'landscape' => {
  return screenWidth > screenHeight ? 'landscape' : 'portrait';
};

// Dynamic styles based on screen size
export const createResponsiveStyles = (styles: any) => {
  return {
    ...styles,
    // Override specific styles for tablets
    ...(isTablet() && {
      container: {
        ...styles.container,
        maxWidth: 600, // Limit max width on tablets
        alignSelf: 'center',
      },
      title: {
        ...styles.title,
        fontSize: responsiveFontSize(36), // Larger title on tablets
      },
      songTitle: {
        ...styles.songTitle,
        fontSize: responsiveFontSize(28), // Larger song titles on tablets
      },
    }),
  };
};
