import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import Card from './Card';

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#a855f7', '#ec4899'];

const THEME = {
  grid: { stroke: '#334155', strokeDasharray: '3 3' },
  axis: { stroke: '#475569', fontSize: 11, fill: '#94a3b8' },
  tooltip: { backgroundColor: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 8 },
};

/**
 * TrendChart — line / area / bar chart wrapped in a Card.
 *
 * Props:
 *   type     – 'line' | 'area' | 'bar' (default 'line')
 *   data     – array of data points
 *   dataKeys – array of Y-axis keys to plot
 *   xKey     – X-axis key (default 'name')
 *   title    – card heading
 *   height   – chart height (default 260)
 */
export default function TrendChart({
  type = 'line',
  data = [],
  dataKeys = [],
  xKey = 'name',
  title,
  height = 260,
}) {
  if (!data.length) {
    return (
      <Card title={title}>
        <div className="flex items-center justify-center text-slate-500 h-40 text-sm">No data available</div>
      </Card>
    );
  }

  const chart = () => {
    switch (type) {
      case 'area':
        return (
          <AreaChart data={data}>
            <CartesianGrid {...THEME.grid} />
            <XAxis dataKey={xKey} {...THEME.axis} />
            <YAxis {...THEME.axis} />
            <Tooltip contentStyle={THEME.tooltip} />
            <Legend />
            {dataKeys.map((key, i) => (
              <Area key={key} type="monotone" dataKey={key} stroke={COLORS[i % COLORS.length]} fill={COLORS[i % COLORS.length]} fillOpacity={0.12} strokeWidth={2} />
            ))}
          </AreaChart>
        );
      case 'bar':
        return (
          <BarChart data={data}>
            <CartesianGrid {...THEME.grid} />
            <XAxis dataKey={xKey} {...THEME.axis} />
            <YAxis {...THEME.axis} />
            <Tooltip contentStyle={THEME.tooltip} />
            <Legend />
            {dataKeys.map((key, i) => (
              <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        );
      default:
        return (
          <LineChart data={data}>
            <CartesianGrid {...THEME.grid} />
            <XAxis dataKey={xKey} {...THEME.axis} />
            <YAxis {...THEME.axis} />
            <Tooltip contentStyle={THEME.tooltip} />
            <Legend />
            {dataKeys.map((key, i) => (
              <Line key={key} type="monotone" dataKey={key} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        );
    }
  };

  return (
    <Card title={title}>
      <ResponsiveContainer width="100%" height={height}>
        {chart()}
      </ResponsiveContainer>
    </Card>
  );
}
