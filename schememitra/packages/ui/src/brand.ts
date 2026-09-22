/**
 * Original SchemeMitra mark: two paths that meet and continue as one — a citizen's route
 * and a lender's route joining. Plain SVG so web and native (react-native-svg) can share it.
 * Deliberately avoids any national emblem, flag or ministry symbol.
 */
export const brandMarkPaths = {
  viewBox: '0 0 48 48',
  left: 'M6 38c6-1 10-5 12-11s5-11 12-12',
  right: 'M42 38c-6-1-10-5-12-11',
  node: { cx: 30, cy: 15, r: 4 },
} as const;

export const brandName = 'SchemeMitra';
