'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CustomerCommunicationStats } from '@/lib/types';

interface CustomerCommunicationBarChartProps {
  stats: CustomerCommunicationStats;
  height?: number;
}

export default function CustomerCommunicationBarChart({
  stats,
  height = 280,
}: CustomerCommunicationBarChartProps) {
  const chartData = [
    {
      channel: 'Email',
      sent: Number(stats?.email?.sent ?? 0),
      received: Number(stats?.email?.received ?? 0),
    },
    {
      channel: 'SMS',
      sent: Number(stats?.sms?.sent ?? 0),
      received: Number(stats?.sms?.received ?? 0),
    },
    {
      channel: 'Phone',
      sent: Number(stats?.phone?.sent ?? 0),
      received: Number(stats?.phone?.received ?? 0),
    },
  ];

  const total = chartData.reduce((sum, row) => sum + row.sent + row.received, 0);
  if (total === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground" style={{ height }}>
        No communications recorded yet
      </div>
    );
  }

  return (
    <div className="w-full" style={{ height, minHeight: height }}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="channel" tick={{ fill: 'var(--muted-foreground)' }} />
          <YAxis allowDecimals={false} tick={{ fill: 'var(--muted-foreground)' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
            }}
          />
          <Legend />
          <Bar dataKey="sent" name="Sent" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="received" name="Received" fill="#22c55e" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
