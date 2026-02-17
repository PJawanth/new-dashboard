import React from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from 'recharts';
import Card from './Card';

const COLORS = ['#ef4444', '#f59e0b', '#eab308', '#22c55e', '#6366f1', '#3b82f6', '#a855f7', '#ec4899'];

/**
 * DonutChart — a pie/donut chart wrapped in a Card.
 *
 * Props:
 *   data      – array of { name, value }
 *   dataKey   – value key (default 'value')
 *   nameKey   – label key (default 'name')
 *   title     – card heading
 *   height    – chart height (default 260)
 *   colors    – optional custom colour array
 */
export default function DonutChart({
  data = [],
  dataKey = 'value',
  nameKey = 'name',
  title,
  height = 260,
  colors,
}) {
  const palette = colors || COLORS;

  // Filter out zero/null entries for cleaner display
  const filtered = data.filter((d) => d[dataKey] != null && d[dataKey] > 0);

  if (!filtered.length) {
    return (
      <Card title={title}>
        <div className="flex items-center justify-center text-slate-500 h-40 text-sm">No data available</div>
      </Card>
    );
  }

  const tooltipStyle = { backgroundColor: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 8 };

  return (
    <Card title={title}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={filtered}
            dataKey={dataKey}
            nameKey={nameKey}
            cx="50%"
            cy="50%"
            innerRadius="55%"
            outerRadius="80%"
            paddingAngle={3}
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
          >
            {filtered.map((_, i) => (
              <Cell key={i} fill={palette[i % palette.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </Card>
  );
}
