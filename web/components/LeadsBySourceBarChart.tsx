'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { LeadSourceCount } from '@/lib/types';

const BAR_COLORS = ['#2563eb', '#7c3aed', '#16a34a', '#ea580c', '#0891b2', '#be185d', '#65a30d', '#4f46e5', '#0d9488', '#9333ea'];

interface LeadsBySourceBarChartProps {
  data: LeadSourceCount[];
}

export default function LeadsBySourceBarChart({ data }: LeadsBySourceBarChartProps) {
  const chartData = (data ?? []).map((item) => ({
    name: (item?.source ?? 'Unknown').replace(/_/g, ' '),
    count: Number(item?.count ?? 0),
  })).filter((d) => d.count > 0);

  if (chartData.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center text-muted-foreground">
        No leads by source for this period
      </div>
    );
  }

  return (
    <div className="h-[280px] w-full min-h-[280px]">
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
          radius={[0, 4, 4, 0]}
          animationDuration={500}
        >
          {chartData.map((_, index) => (
            <Cell key={`cell-${index}`} fill={BAR_COLORS[index % BAR_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
    </div>
  );
}
