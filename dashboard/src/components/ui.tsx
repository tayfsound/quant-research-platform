import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div
      className={`bg-surface border border-line rounded-xl shadow-layer-1 hover:shadow-layer-2 min-w-0 overflow-hidden ${
        padded ? "p-5" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink tracking-tight">{title}</h1>
        {description && <p className="text-sm text-ink-soft mt-1 max-w-xl">{description}</p>}
      </div>
      {action}
    </div>
  );
}

const badgeTones = {
  neutral: "bg-canvas-soft text-ink-soft border-line",
  accent: "bg-accent-soft text-accent-ink border-transparent",
  rise: "bg-rise-soft text-rise border-transparent",
  fall: "bg-fall-soft text-fall border-transparent",
  warn: "bg-warn-soft text-warn border-transparent",
};

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: keyof typeof badgeTones }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${badgeTones[tone]}`}>
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  type?: "button" | "submit";
  className?: string;
}) {
  const base = "px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]";
  const variants = {
    primary: "bg-accent text-white shadow-layer-1 hover:shadow-layer-2 hover:brightness-110",
    secondary: "bg-canvas-soft text-ink border border-line hover:bg-surface-soft",
    danger: "bg-fall text-white hover:brightness-110",
    ghost: "text-ink-soft hover:bg-canvas-soft",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Input({
  value,
  onChange,
  placeholder,
  type = "text",
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  className?: string;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      type={type}
      className={`w-full px-3 py-2 rounded-lg bg-canvas-soft border border-line text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent ${className}`}
    />
  );
}

export function StatCard({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: keyof typeof badgeTones;
}) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-ink-faint font-medium break-words">{label}</p>
      <p
        className={`text-2xl font-semibold mt-2 break-words leading-tight ${tone === "rise" ? "text-rise" : tone === "fall" ? "text-fall" : "text-ink"}`}
        title={typeof value === "string" || typeof value === "number" ? String(value) : undefined}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-ink-soft mt-1 break-words">{sub}</p>}
    </Card>
  );
}

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="text-center py-12 text-ink-faint text-sm border border-dashed border-line rounded-xl">
      {label}
    </div>
  );
}

export function Spinner() {
  return (
    <span className="inline-block w-4 h-4 border-2 border-accent-soft border-t-accent rounded-full animate-spin" />
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="bg-fall-soft border border-fall/20 text-fall rounded-lg px-3 py-2 text-sm mb-4">
      {children}
    </div>
  );
}

export function CodeBlock({ children }: { children: ReactNode }) {
  return (
    <pre className="whitespace-pre-wrap text-xs mt-2 bg-canvas-soft rounded-lg p-3 text-ink-soft font-mono overflow-x-auto">
      {children}
    </pre>
  );
}
