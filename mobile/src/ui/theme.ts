import { useColorScheme } from 'react-native';

export interface Theme {
  bg: string;
  card: string;
  text: string;
  muted: string;
  primary: string;
  primaryText: string;
  danger: string;
  warn: string;
  border: string;
}

const LIGHT: Theme = {
  bg: '#f4f6f8',
  card: '#ffffff',
  text: '#14181c',
  muted: '#566370',
  primary: '#0b57d0',
  primaryText: '#ffffff',
  danger: '#b3261e',
  warn: '#8a5a00',
  border: '#d3d9df',
};

const DARK: Theme = {
  bg: '#0e1114',
  card: '#1b2025',
  text: '#eef1f4',
  muted: '#a3afba',
  primary: '#8ab4f8',
  primaryText: '#0b1626',
  danger: '#f2b8b5',
  warn: '#f5c26b',
  border: '#33404b',
};

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? DARK : LIGHT;
}
