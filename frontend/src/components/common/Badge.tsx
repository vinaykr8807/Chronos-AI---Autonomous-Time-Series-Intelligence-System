import { motion } from 'framer-motion';

type BadgeVariant = 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  pulse?: boolean;
  className?: string;
}

export function Badge({ children, variant = 'primary', size = 'md', pulse = false, className = '' }: BadgeProps) {
  const variants = {
    primary: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40',
    secondary: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
    success: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    warning: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    error: 'bg-red-500/20 text-red-300 border-red-500/40',
    info: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-xs',
  };

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`
        inline-flex items-center gap-1 font-medium rounded-full border
        ${variants[variant]}
        ${sizes[size]}
        ${className}
      `}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
        </span>
      )}
      {children}
    </motion.span>
  );
}

interface StatusBadgeProps {
  status: 'ready' | 'processing' | 'complete' | 'error' | 'validated';
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const config = {
    ready: { variant: 'info' as BadgeVariant, text: 'Ready' },
    processing: { variant: 'warning' as BadgeVariant, text: 'Processing' },
    complete: { variant: 'success' as BadgeVariant, text: 'Complete' },
    error: { variant: 'error' as BadgeVariant, text: 'Error' },
    validated: { variant: 'success' as BadgeVariant, text: 'TS Validated' },
  };

  return (
    <Badge variant={config[status].variant} pulse={status === 'processing'}>
      {label || config[status].text}
    </Badge>
  );
}
