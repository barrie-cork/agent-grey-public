/**
 * Reporting Charts Module
 * Handles all chart visualizations for the reporting app
 */

class ReportingCharts {
    constructor() {
        this.chart_instances = {};
        this.chart_colors = {
            primary: '#3498db',
            success: '#27ae60',
            warning: '#f39c12',
            danger: '#e74c3c',
            info: '#00bcd4',
            secondary: '#95a5a6'
        };
    }

    /**
     * Initialize PRISMA flow diagram (deprecated - use PRISMA2020Diagram instead)
     */
    initialize_prisma_flow(canvas_id, flow_data) {
        console.warn('initialize_prisma_flow is deprecated. Use PRISMA2020Diagram class instead.');
        // This method is kept for backward compatibility but does nothing
    }

    /**
     * Initialize performance metrics charts
     */
    initialize_performance_metrics(canvas_id, metrics_data) {
        const ctx = document.getElementById(canvas_id).getContext('2d');

        if (this.chart_instances.performance) {
            this.chart_instances.performance.destroy();
        }

        const success_rate = (metrics_data.successful_executions / metrics_data.total_executions * 100).toFixed(1);
        const failure_rate = (100 - success_rate).toFixed(1);

        this.chart_instances.performance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: [`Successful (${success_rate}%)`, `Failed (${failure_rate}%)`],
                datasets: [{
                    data: [
                        metrics_data.successful_executions,
                        metrics_data.total_executions - metrics_data.successful_executions
                    ],
                    backgroundColor: [
                        this.chart_colors.success,
                        this.chart_colors.danger
                    ],
                    hoverBackgroundColor: [
                        'rgba(39, 174, 96, 0.8)',
                        'rgba(231, 76, 60, 0.8)'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Search Execution Success Rate',
                        font: {
                            size: 16
                        }
                    },
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 15,
                            font: {
                                size: 12
                            }
                        }
                    }
                },
                cutout: '60%'
            }
        });
    }

    /**
     * Initialize quality distribution chart
     */
    initialize_quality_distribution(canvas_id, quality_data) {
        const ctx = document.getElementById(canvas_id).getContext('2d');

        if (this.chart_instances.quality) {
            this.chart_instances.quality.destroy();
        }

        const labels = Object.keys(quality_data.distribution);
        const data = labels.map(key => quality_data.distribution[key].count);

        this.chart_instances.quality = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Number of Results',
                    data: data,
                    backgroundColor: labels.map(label => {
                        if (label.includes('0.7')) return this.chart_colors.success;
                        if (label.includes('0.4')) return this.chart_colors.warning;
                        return this.chart_colors.danger;
                    }),
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Quality Score Distribution',
                        font: {
                            size: 16
                        }
                    },
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Number of Results'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Quality Score Range'
                        }
                    }
                }
            }
        });
    }

    /**
     * Initialize exclusion reasons chart
     */
    initialize_exclusion_reasons(canvas_id, exclusion_data) {
        const ctx = document.getElementById(canvas_id).getContext('2d');

        if (this.chart_instances.exclusions) {
            this.chart_instances.exclusions.destroy();
        }

        const labels = Object.keys(exclusion_data.reasons || {});
        const data = labels.map(key => exclusion_data.reasons[key].count);

        this.chart_instances.exclusions = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: [
                        this.chart_colors.danger,
                        this.chart_colors.warning,
                        this.chart_colors.info,
                        this.chart_colors.secondary,
                        this.chart_colors.primary
                    ],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Exclusion Reasons Distribution',
                        font: {
                            size: 16
                        }
                    },
                    legend: {
                        position: 'right',
                        labels: {
                            padding: 15,
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Update chart data dynamically
     */
    update_chart_data(chart_type, new_data) {
        if (this.chart_instances[chart_type]) {
            this.chart_instances[chart_type].data = new_data;
            this.chart_instances[chart_type].update();
        }
    }

    /**
     * Destroy a specific chart
     */
    destroy_chart(chart_type) {
        if (this.chart_instances[chart_type]) {
            this.chart_instances[chart_type].destroy();
            delete this.chart_instances[chart_type];
        }
    }

    /**
     * Destroy all charts
     */
    destroy_all_charts() {
        Object.keys(this.chart_instances).forEach(chart_type => {
            this.destroy_chart(chart_type);
        });
    }

    /**
     * Export chart as image
     */
    export_chart_as_image(chart_type, filename = 'chart.png') {
        if (this.chart_instances[chart_type]) {
            const canvas = this.chart_instances[chart_type].canvas;
            const url = canvas.toDataURL('image/png');

            const link = document.createElement('a');
            link.download = filename;
            link.href = url;
            link.click();
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    window.report_charts = new ReportingCharts();

    // PRISMA flow chart initialization removed - use PRISMA2020Diagram instead

    if (window.performanceMetrics) {
        report_charts.initialize_performance_metrics('performanceChart', window.performanceMetrics);
    }

    if (window.qualityDistribution) {
        report_charts.initialize_quality_distribution('qualityChart', window.qualityDistribution);
    }

    if (window.exclusionAnalysis) {
        report_charts.initialize_exclusion_reasons('exclusionChart', window.exclusionAnalysis);
    }
});

// Export functionality
function export_chart(chart_type) {
    if (window.report_charts) {
        const filename = `${chart_type}_${new Date().toISOString().split('T')[0]}.png`;
        window.report_charts.export_chart_as_image(chart_type, filename);
    }
}

// Legacy compatibility
window.exportChart = export_chart;
