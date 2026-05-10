import { motion } from 'framer-motion';

interface PageContainerProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  fullWidth?: boolean;
}

export function PageContainer({
  children,
  title,
  subtitle,
  action,
  fullWidth = false,
}: PageContainerProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="min-h-[calc(100vh-4rem)] pb-12"
    >
      {(title || action) && (
        <div className="border-b border-space-600 bg-space-900/50">
          <div className={`max-w-7xl mx-auto px-6 py-6 ${fullWidth ? '' : 'lg:px-8'}`}>
            <div className="flex items-center justify-between">
              <div>
                {title && (
                  <h1 className="text-2xl font-bold text-white">{title}</h1>
                )}
                {subtitle && (
                  <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
                )}
              </div>
              {action && <div>{action}</div>}
            </div>
          </div>
        </div>
      )}
      <div className={`${fullWidth ? '' : 'max-w-7xl mx-auto px-6 lg:px-8'}`}>
        {children}
      </div>
    </motion.div>
  );
}

interface SectionProps {
  children: React.ReactNode;
  title?: string;
  description?: string;
  className?: string;
  noPadding?: boolean;
}

export function Section({
  children,
  title,
  description,
  className = '',
  noPadding = false,
}: SectionProps) {
  return (
    <section className={`${noPadding ? '' : 'py-8'} ${className}`}>
      {title && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          {description && (
            <p className="mt-1 text-sm text-slate-400">{description}</p>
          )}
        </div>
      )}
      {children}
    </section>
  );
}

interface GridProps {
  children: React.ReactNode;
  columns?: 1 | 2 | 3 | 4;
  gap?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function Grid({ children, columns = 3, gap = 'md', className = '' }: GridProps) {
  const columnClasses = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
  };

  const gapClasses = {
    sm: 'gap-4',
    md: 'gap-6',
    lg: 'gap-8',
  };

  return (
    <div className={`grid ${columnClasses[columns]} ${gapClasses[gap]} ${className}`}>
      {children}
    </div>
  );
}
