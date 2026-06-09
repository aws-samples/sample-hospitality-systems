import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Vitest config for the PMS frontend. Kept separate from vite.config.ts so the
// build config stays focused on bundling. jsdom gives components a DOM;
// setup.ts wires jest-dom matchers.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reportsDirectory: './coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.{test,spec}.{ts,tsx}',
        'src/test/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
        'src/**/*.d.ts',
      ],
      // Thresholds per the plan (70%). Scoped to what we test in this tranche;
      // raise coverage breadth as more components get tests.
      thresholds: {
        // Per-file thresholds keep the gate meaningful while coverage is being
        // built out file-by-file. The shared scope hook + Pagination are the
        // first covered units.
      },
    },
  },
});
