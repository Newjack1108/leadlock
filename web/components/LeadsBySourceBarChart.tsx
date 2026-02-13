'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { LeadSourceCount } from '@/lib/types';

interface LeadsBySourceBarChartProps {
  data: LeadSourceCount[];
}

export default function LeadsBySourceBarChart({ data }: LeadsBySourceBarChartProps) {
  const chartData = data.map((item) => ({
    name: item.source.replace(/_/g, ' '),
    count: item.count,
  }));

  if (chartData.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center text-muted-foreground">
        No leads by source for this period
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" tick={{ fill: 'var(--muted-foreground)' }} />
        <YAxis
          type="category"
          dataKey="name"
          width={100}
          tick={{ fill: 'var(--muted-foreground)' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
          }}
          formatter={(value?: number) => [value ?? 0, 'Leads']}
        />
        <Bar
          dataKey="count"
          fill="var(--primary)"
          radius={[0, 4, 4, 0]}
          animationDuration={500}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
