'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

const STATUS_COLORS = ['#1F6B3A', '#3FA86B', '#10B981', '#6B7280', '#9CA3AF'];

interface StatusPieChartProps {
  newCount: number;
  quotedCount: number;
  wonCount: number;
  lostCount: number;
}

export default function StatusPieChart({ newCount, quotedCount, wonCount, lostCount }: StatusPieChartProps) {
  const data = [
    { name: 'New', value: newCount },
    { name: 'Quoted', value: quotedCount },
    { name: 'Won', value: wonCount },
    { name: 'Lost', value: lostCount },
  ].filter((d) => d.value > 0);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  if (total === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center text-muted-foreground">
        No data for this period
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          animationDuration={500}
        >
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={STATUS_COLORS[index % STATUS_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
          }}
          formatter={(value?: number) => [value ?? 0, '']}
        />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
