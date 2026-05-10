import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: 'primary' | 'secondary' | 'accent' | null;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  onClick?: () => void;
}

export function Card({
  children,
  className = '',
  hover = false,
  glow = null,
  padding = 'md',
  onClick
}: CardProps) {
  const paddingStyles = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
  };

  const glowStyles = {
    primary: 'hover:shadow-[0_0_30px_rgba(99,102,241,0.3)]',
    secondary: 'hover:shadow-[0_0_30px_rgba(34,211,238,0.3)]',
    accent: 'hover:shadow-[0_0_30px_rgba(244,114,182,0.3)]',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      whileHover={hover ? { scale: 1.02 } : {}}
      onClick={onClick}
      className={`
        bg-space-800 border border-space-600 rounded-xl
        ${paddingStyles[padding]}
        ${hover ? 'cursor-pointer transition-all duration-300 hover:border-space-500' : ''}
        ${glow ? glowStyles[glow] : ''}
        ${className}
      `}
    >
      {children}
    </motion.div>
  );
}

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  trend?: {
    direction: 'up' | 'down' | 'neutral';
    value: string;
  };
  className?: string;
}

export function StatCard({ icon: Icon, label, value, trend, className = '' }: StatCardProps) {
  const trendColors = {
    up: 'text-success',
    down: 'text-error',
    neutral: 'text-slate-400',
  };

  const trendIcons = {
    up: '↑',
    down: '↓',
    neutral: '→',
  };

  return (
    <Card className={`relative overflow-hidden ${className}`}>
      <div className="flex items-start justify-between">
        <div className="p-2 rounded-lg bg-gradient-to-br from-indigo-500/20 to-indigo-600/10">
          <Icon className="w-5 h-5 text-indigo-400" />
        </div>
        {trend && (
          <span className={`text-sm font-medium ${trendColors[trend.direction]}`}>
            {trendIcons[trend.direction]} {trend.value}
          </span>
        )}
      </div>
      <div className="mt-4">
        <p className="text-sm text-slate-400">{label}</p>
        <p className="mt-1 text-2xl font-bold text-white font-mono">{value}</p>
      </div>
    </Card>
  );
}
