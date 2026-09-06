import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0b0f17",
          raised: "#111826",
          border: "#1f2937",
        },
        // Severity/status quad — from the dataviz skill's fixed status palette
        // (good/warning/serious/critical), mapped onto LOW/MEDIUM/HIGH/CRITICAL.
        // Never reused for chart series identity — see docs on chart colors below.
        severity: {
          low: "#0ca30c",
          medium: "#fab219",
          high: "#ec835a",
          critical: "#d03b3b",
        },
        // Fixed categorical series order for charts (dark-mode steps, dataviz skill).
        // Assign in this order, never cycled/reused for a different series.
        chart: {
          1: "#3987e5", // blue
          2: "#d95926", // orange
          3: "#199e70", // aqua
          4: "#c98500", // yellow
          5: "#d55181", // magenta
          6: "#008300", // green
          7: "#9085e9", // violet
          8: "#e66767", // red
          grid: "#2c2c2a",
          axis: "#383835",
          muted: "#898781",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
