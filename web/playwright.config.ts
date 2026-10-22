import { defineConfig } from "@playwright/test";

// End-to-end checks against the production build (`npm run build -w web` first).
export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    browserName: "chromium",
    baseURL: "http://localhost:4318",
    // Overlay audio must start without a tap, as it would after the viewer taps "Sound on".
    launchOptions: { args: ["--autoplay-policy=no-user-gesture-required"] },
  },
  webServer: {
    command: "npx vite preview --port 4318 --strictPort",
    url: "http://localhost:4318",
    reuseExistingServer: false,
  },
});
