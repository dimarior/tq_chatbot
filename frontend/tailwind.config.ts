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
      colors: {
        brand: {
          DEFAULT: "#2563eb", // blue-600 (TQ accent)
          dark: "#1d4ed8",
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
