'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

const STATUS_COLORS: Record<string, string> = {
  New: '#2563eb',
  Quoted: '#7c3aed',
  Won: '#16a34a',
  Lost: '#dc2626',
};

interface StatusPieChartProps {
  newCount: number;
  quotedCount: number;
  wonCount: number;
  lostCount: number;
  height?: number;
}

export default function StatusPieChart({ newCount, quotedCount, wonCount, lostCount, height = 280 }: StatusPieChartProps) {
  const data = [
    { name: 'New', value: Number(newCount ?? 0), color: STATUS_COLORS.New },
    { name: 'Quoted', value: Number(quotedCount ?? 0), color: STATUS_COLORS.Quoted },
    { name: 'Won', value: Number(wonCount ?? 0), color: STATUS_COLORS.Won },
    { name: 'Lost', value: Number(lostCount ?? 0), color: STATUS_COLORS.Lost },
  ].filter((d) => d.value > 0);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  if (total === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground" style={{ height }}>
        No data for this period
      </div>
    );
  }

  const scale = height / 280;
  const innerRadius = Math.round(60 * scale);
  const outerRadius = Math.round(100 * scale);

  return (
    <div className="w-full" style={{ height, minHeight: height }}>
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={innerRadius}
          outerRadius={outerRadius}
          paddingAngle={2}
          dataKey="value"
          animationDuration={500}
        >
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
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
    </div>
  );
}
