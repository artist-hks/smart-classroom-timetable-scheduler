const VARIANTS = {
  primary: "bg-ink text-white hover:bg-ink-600 border border-ink disabled:bg-ink-400 disabled:border-ink-400",
  secondary: "bg-surface text-ink border border-line hover:border-ink-400 hover:bg-ink-50",
  ghost: "bg-transparent text-ink border border-transparent hover:bg-ink-50",
  danger: "bg-danger text-white border border-danger hover:bg-danger/90",
  gold: "bg-gold text-white border border-gold hover:bg-gold-600",
};

const SIZES = {
  sm: "text-xs px-2.5 py-1.5 gap-1.5",
  md: "text-sm px-3.5 py-2 gap-2",
  lg: "text-sm px-4.5 py-2.5 gap-2",
};

export default function Button({
  variant = "primary",
  size = "md",
  className = "",
  as: Comp = "button",
  icon: Icon,
  children,
  ...props
}) {
  return (
    <Comp
      className={`inline-flex items-center justify-center rounded font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {Icon && <Icon size={size === "sm" ? 14 : 16} />}
      {children}
    </Comp>
  );
}
