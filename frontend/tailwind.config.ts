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
        // Estructura ChatGPT (neutrales) + acentos de marca Tecnoquímicas.
        canvas: "#ffffff",
        panel: "#f5f7fb", // sidebar con tinte índigo muy sutil
        panelHover: "#e6ebf6",
        panelActive: "#d8e0f1",
        bubble: "#f4f4f4",
        ink: {
          DEFAULT: "#0d1430",
          muted: "#525a78",
          subtle: "#8b91a8",
        },
        line: "#e2e6ee",
        // Marca Tecnoquímicas: índigo (primario) + cian (secundario).
        // Tomados del sitio oficial: #323FA7 (botones) y #009CDE (hero).
        brand: {
          DEFAULT: "#323FA7",
          dark: "#262f80",
          light: "#4a57c4",
          accent: "#009CDE",
          accentDark: "#0079ad",
        },
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #323FA7 0%, #009CDE 100%)",
      },
      boxShadow: {
        composer:
          "0 0 0 1px rgba(50,63,167,0.06), 0 2px 6px rgba(0,156,222,0.04), 0 8px 24px rgba(0,0,0,0.06)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
