/**
 * Chart.js configuration builders for Kappa trend charts.
 */

import type { IRRMetric } from '../types';

interface ChartColors {
  primary: string;
  primaryLight: string;
  warning: string;
}

export function getChartColorsFromCSS(): ChartColors {
  const styles = getComputedStyle(document.documentElement);
  return {
    primary: styles.getPropertyValue('--color-deep-navy').trim() || 'oklch(0.25 0.05 250)',
    primaryLight: 'oklch(0.25 0.05 250 / 0.1)',
    warning: styles.getPropertyValue('--color-warning').trim() || 'oklch(0.78 0.16 75)',
  };
}

export function formatChartDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-GB', {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateString;
  }
}

export function buildKappaTrendChartData(irrTrend: IRRMetric[], colors: ChartColors) {
  if (!irrTrend || irrTrend.length === 0) {
    return { labels: [], datasets: [] };
  }

  return {
    labels: irrTrend.map((d) => formatChartDate(d.calculated_at)),
    datasets: [
      {
        label: "Cohen's Kappa",
        data: irrTrend.map((d) => d.cohens_kappa),
        borderColor: colors.primary,
        backgroundColor: colors.primaryLight,
        fill: true,
        tension: 0.4,
        pointRadius: 5,
        pointHoverRadius: 7,
      },
      {
        label: 'Cochrane Threshold (0.70)',
        data: irrTrend.map(() => 0.70),
        borderColor: colors.warning,
        borderDash: [5, 5],
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
      },
    ],
  };
}

export function buildKappaTrendChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'top' as const,
        labels: {
          font: {
            family: 'Inter, sans-serif',
            size: 10,
            weight: 'bold' as const,
          },
          usePointStyle: true,
          padding: 20,
        },
      },
      tooltip: {
        backgroundColor: 'rgba(10, 25, 41, 0.9)',
        titleFont: {
          family: 'Inter, sans-serif',
          size: 11,
          weight: 'bold' as const,
        },
        bodyFont: {
          family: 'Inter, sans-serif',
          size: 10,
        },
        padding: 12,
        cornerRadius: 4,
        callbacks: {
          label: function(context: any) {
            const label = context.dataset.label || '';
            const value = context.parsed.y.toFixed(3);
            return `${label}: ${value}`;
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 1.0,
        grid: {
          color: 'rgba(230, 235, 241, 0.5)',
          drawBorder: false,
        },
        ticks: {
          stepSize: 0.2,
          font: {
            family: 'JetBrains Mono, monospace',
            size: 10,
          },
          padding: 10,
        },
        title: {
          display: true,
          text: "KAPPA COEFFICIENT (\u03BA)",
          font: {
            family: 'Inter, sans-serif',
            size: 10,
            weight: 'bold' as const,
          },
          padding: { top: 10, bottom: 0 },
        },
      },
      x: {
        grid: {
          display: false,
        },
        ticks: {
          font: {
            family: 'Inter, sans-serif',
            size: 10,
          },
          padding: 10,
        },
        title: {
          display: true,
          text: 'TEMPORAL PROGRESSION',
          font: {
            family: 'Inter, sans-serif',
            size: 10,
            weight: 'bold' as const,
          },
        },
      },
    },
  };
}
