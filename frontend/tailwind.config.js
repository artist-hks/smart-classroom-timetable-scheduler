/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#14213D",
          50: "#EEF1F6",
          100: "#DCE1EC",
          400: "#3D4E75",
          600: "#233256",
          700: "#1A2745",
          900: "#0F1830",
        },
        paper: "#F6F5F1",
        surface: "#FFFFFF",
        line: "#E1DED4",
        slate: {
          DEFAULT: "#5B6472",
          400: "#7C8494",
          500: "#5B6472",
          600: "#454C58",
        },
        gold: {
          DEFAULT: "#A8762C",
          50: "#F8F1E4",
          100: "#EEDFC0",
          600: "#8C611F",
        },
        success: { DEFAULT: "#1F7A4D", 50: "#E7F4EC" },
        warning: { DEFAULT: "#B0700B", 50: "#FBF0DD" },
        danger: { DEFAULT: "#AB3A3A", 50: "#F8E9E9" },
        info: { DEFAULT: "#2A5C9A", 50: "#E9EFF7" },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 24, 48, 0.06)",
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "10px",
      },
      keyframes: {
        "toast-in": {
          "0%": { opacity: 0, transform: "translateY(6px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        "modal-in": {
          "0%": { opacity: 0, transform: "scale(0.97)" },
          "100%": { opacity: 1, transform: "scale(1)" },
        },
      },
    },
  },
  plugins: [],
}

