'use client';

import React from 'react';
import dynamic from 'next/dynamic';

// Dynamically import ApexCharts to avoid SSR issues
const Chart = dynamic(() => import('react-apexcharts'), { ssr: false });

export interface PieChartData {
  name: string;
  value: number;
}

export interface PieChartProps {
  data: PieChartData[];
  size?: number | string;
  showLabels?: boolean;
  showLegend?: boolean;
  className?: string;
  title?: string;
}

// Lio-aligned categorical palette: anchored on the cyan/teal + ink family,
// with a few muted complementary hues for larger series.
const CHART_COLORS = [
  '#0c6f80', // accent-deep (teal)
  '#6fc7d8', // accent (cyan)
  '#1d2530', // ink
  '#4b9aa8', // muted teal
  '#c9a24a', // muted amber
  '#3a8f7d', // muted green
  '#7d8896', // slate
  '#155e6b', // deep teal
  '#a9cfd8', // pale cyan
  '#576270', // graphite
];

export function PieChart({
  data,
  size = 300,
  showLabels = true,
  showLegend = true,
  className = '',
  title = '',
}: PieChartProps) {
  // Safety check for data
  if (!data || data.length === 0) {
    return (
      <div className={`flex w-full items-center justify-center ${className}`}>
        <p className="text-gray-400">No data available</p>
      </div>
    );
  }

  const chartOptions: ApexCharts.ApexOptions = {
    chart: {
      type: 'pie',
      background: 'transparent',
      animations: {
        enabled: true,
      },
    },
    labels: data.map((item) => item.name),
    colors: CHART_COLORS,
    legend: {
      show: showLegend,
      position: 'bottom',
      labels: {
        colors: '#4b5563',
      },
    },
    dataLabels: {
      enabled: showLabels,
      style: {
        colors: ['#ffffff'],
      },
    },
    plotOptions: {
      pie: {
        expandOnClick: false,
        donut: {
          labels: {
            show: false,
          },
        },
      },
    },
    theme: {
      mode: 'light',
    },
    noData: {
      text: 'No data available',
      style: {
        color: '#9ca3af',
      },
    },
    tooltip: {
      y: {
        formatter: (val) => {
          return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        },
      },
    },
  };

  const series = data.map((item) => item.value);

  return (
    <div className={`w-full ${className}`}>
      {title && <h3 className="text-lg font-semibold text-gray-900 mb-4 text-center">{title}</h3>}
      <Chart options={chartOptions} series={series} type="pie" width={size} height={size} />
    </div>
  );
}

