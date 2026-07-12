import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0f",
        surface: "#13131c",
        surface2: "#1c1c28",
        border: "#2a2a3a",
        muted: "#8b8b9e",
      },
    },
  },
  plugins: [],
} satisfies Config;
