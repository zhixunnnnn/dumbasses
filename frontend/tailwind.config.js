/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#161514",
        surface: "#1e1d1b",
        raised: "#26241f",
        hairline: "rgba(255,255,255,0.08)",
        txt: "#ededeb",
        muted: "#9a968e",
        faint: "#6a665f",
        pos: "#3ecf8e",
        neg: "#ef6f63",
        leaders: "#3ecf8e",
        profit: "#e0b24a",
        purpose: "#4cc4d4",
        laggards: "#ec6a5e",
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "monospace",
        ],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.03), 0 12px 32px rgba(0,0,0,0.35)",
        float: "0 18px 48px rgba(0,0,0,0.55)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s cubic-bezier(0.22,1,0.36,1) both",
      },
    },
  },
  plugins: [],
};
