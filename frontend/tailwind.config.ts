import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./node_modules/@assistant-ui/react/dist/**/*.{js,mjs}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      colors: {
        // ChatGPT-style neutral palette (light theme).
        canvas: "#ffffff",
        panel: "#f9f9f9",
        panelHover: "#ececec",
        panelActive: "#e3e3e3",
        bubble: "#f4f4f4",
        ink: {
          DEFAULT: "#0d0d0d",
          muted: "#5d5d5d",
          subtle: "#8e8e8e",
        },
        line: "#e5e5e5",
        brand: {
          DEFAULT: "#0d0d0d",
          dark: "#000000",
        },
      },
      boxShadow: {
        composer:
          "0 0 0 1px rgba(0,0,0,0.04), 0 2px 6px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
