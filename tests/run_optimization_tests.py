#!/usr/bin/env python3
"""
Optimization Testing Suite Runner

This script runs the comprehensive optimization validation test suite and generates
detailed reports showing the performance impact of the task optimizations:

1. CELERY_BEAT_SCHEDULE optimization (15+ tasks → 9 tasks)
2. Unified monitoring frequency (30s → 120s) 
3. Activity-based monitoring intervals
4. System load reduction validation

Usage:
    python run_optimization_tests.py [options]

Options:
    --test-type: specific test type (all, performance, edge-cases, user-journey)
    --report-format: output format (json, html, markdown)
    --output-dir: directory for test results and reports
    --headless: run browser tests in headless mode
    --parallel: number of parallel test processes
    --verbose: enable verbose logging
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.test')

import django

django.setup()

from django.core.management import execute_from_command_line

logger = logging.getLogger(__name__)


class OptimizationTestRunner:
    """Comprehensive test runner for optimization validation."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.test_results = {
            'start_time': datetime.now().isoformat(),
            'configuration': config,
            'test_suites': {},
            'performance_metrics': {},
            'optimization_validation': {},
            'errors': []
        }
        
        # Set up output directories
        self.output_dir = Path(config['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        (self.output_dir / 'screenshots').mkdir(exist_ok=True)
        (self.output_dir / 'videos').mkdir(exist_ok=True)
        (self.output_dir / 'reports').mkdir(exist_ok=True)
        (self.output_dir / 'logs').mkdir(exist_ok=True)
        
        # Configure logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up comprehensive logging for test run."""
        log_level = logging.DEBUG if self.config['verbose'] else logging.INFO
        
        # File handler
        log_file = self.output_dir / 'logs' / f'optimization_tests_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    
    def run_optimization_tests(self) -> Dict[str, Any]:
        """Run the complete optimization test suite."""
        logger.info("🚀 Starting comprehensive optimization validation tests")
        logger.info(f"Configuration: {self.config}")
        
        try:
            # 1. Environment validation
            self._validate_environment()
            
            # 2. Database setup
            self._setup_test_database()
            
            # 3. Start services
            self._start_test_services()
            
            # 4. Run test suites based on configuration
            if self.config['test_type'] in ['all', 'user-journey']:
                self._run_user_journey_tests()
            
            if self.config['test_type'] in ['all', 'performance']:
                self._run_performance_tests()
            
            if self.config['test_type'] in ['all', 'edge-cases']:
                self._run_edge_case_tests()
            
            # 5. Collect system metrics
            self._collect_system_metrics()
            
            # 6. Validate optimizations
            self._validate_optimizations()
            
            # 7. Generate reports
            self._generate_reports()
            
        except Exception as e:
            logger.error(f"Test run failed: {e}", exc_info=True)
            self.test_results['errors'].append({
                'type': 'test_run_failure',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
            
        finally:
            # 8. Cleanup
            self._cleanup_test_environment()
            
            # 9. Finalize results
            self.test_results['end_time'] = datetime.now().isoformat()
            self.test_results['duration_seconds'] = (
                datetime.fromisoformat(self.test_results['end_time']) -
                datetime.fromisoformat(self.test_results['start_time'])
            ).total_seconds()
        
        return self.test_results
    
    def _validate_environment(self):
        """Validate test environment requirements."""
        logger.info("🔍 Validating test environment")
        
        # Check Docker services
        docker_services = ['web', 'db', 'redis', 'celery_worker', 'celery_beat']
        
        try:
            result = subprocess.run(
                ['docker-compose', 'ps', '--services', '--filter', 'status=running'],
                capture_output=True, text=True, cwd=project_root
            )
            running_services = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            missing_services = [svc for svc in docker_services if svc not in running_services]
            if missing_services:
                raise Exception(f"Required Docker services not running: {missing_services}")
                
            logger.info(f"✅ Docker services validated: {running_services}")
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to check Docker services: {e}")
        
        # Check Playwright installation
        try:
            subprocess.run(['playwright', '--version'], check=True, capture_output=True)
            logger.info("✅ Playwright installation validated")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("⚠️  Playwright not found, installing...")
            subprocess.run(['python', '-m', 'playwright', 'install'], check=True)
        
        # Validate Django settings
        try:
            from django.core.management import execute_from_command_line
            execute_from_command_line(['manage.py', 'check', '--deploy'])
            logger.info("✅ Django configuration validated")
        except Exception as e:
            logger.warning(f"⚠️  Django check warnings: {e}")
    
    def _setup_test_database(self):
        """Set up test database with required data."""
        logger.info("🗄️  Setting up test database")
        
        try:
            # Run migrations
            execute_from_command_line(['manage.py', 'migrate', '--verbosity=0'])
            
            # Create test superuser if needed
            create_superuser_cmd = [
                'python', 'manage.py', 'shell', '-c',
                """
from apps.core.tests.utils import create_test_superuser
admin = create_test_superuser(username_prefix="optimization_admin")
print(f'Test superuser created: {admin.username}')
"""
            ]
            
            subprocess.run(create_superuser_cmd, cwd=project_root, check=True)
            logger.info("✅ Test database setup completed")
            
        except Exception as e:
            raise Exception(f"Database setup failed: {e}")
    
    def _start_test_services(self):
        """Start required services for testing."""
        logger.info("🚀 Starting test services")
        
        try:
            # Ensure services are up
            subprocess.run(
                ['docker-compose', 'up', '-d'], 
                cwd=project_root, check=True
            )
            
            # Wait for services to be ready
            time.sleep(10)
            
            # Health check
            health_check_cmd = [
                'docker-compose', 'exec', '-T', 'web',
                'python', 'manage.py', 'shell', '-c',
                'from django.db import connection; connection.ensure_connection(); print("DB connected")'
            ]
            
            subprocess.run(health_check_cmd, cwd=project_root, check=True)
            logger.info("✅ Test services started and healthy")
            
        except Exception as e:
            raise Exception(f"Failed to start test services: {e}")
    
    def _run_user_journey_tests(self):
        """Run comprehensive user journey tests."""
        logger.info("👥 Running user journey tests")
        
        test_command = [
            'python', '-m', 'pytest',
            'tests/playwright/test_optimization_user_validation.py',
            '-v', '--tb=short',
            f'--html={self.output_dir}/reports/user_journey_report.html',
            '--self-contained-html',
            f'--junitxml={self.output_dir}/reports/user_journey_junit.xml'
        ]
        
        if self.config['headless']:
            test_command.extend(['--headed=false'])
        
        try:
            result = subprocess.run(
                test_command, 
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            self.test_results['test_suites']['user_journey'] = {
                'command': ' '.join(test_command),
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }
            
            if result.returncode == 0:
                logger.info("✅ User journey tests completed successfully")
            else:
                logger.error(f"❌ User journey tests failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("❌ User journey tests timed out")
            self.test_results['test_suites']['user_journey'] = {
                'command': ' '.join(test_command),
                'return_code': -1,
                'error': 'Test timeout after 30 minutes'
            }
    
    def _run_performance_tests(self):
        """Run performance optimization tests."""
        logger.info("⚡ Running performance optimization tests")
        
        test_command = [
            'python', '-m', 'pytest',
            'tests/playwright/test_performance_optimization.py',
            '-v', '--tb=short',
            f'--html={self.output_dir}/reports/performance_report.html',
            '--self-contained-html',
            f'--junitxml={self.output_dir}/reports/performance_junit.xml'
        ]
        
        if self.config['headless']:
            test_command.extend(['--headed=false'])
        
        try:
            result = subprocess.run(
                test_command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=2400  # 40 minutes timeout
            )
            
            self.test_results['test_suites']['performance'] = {
                'command': ' '.join(test_command),
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }
            
            if result.returncode == 0:
                logger.info("✅ Performance tests completed successfully")
            else:
                logger.error(f"❌ Performance tests failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Performance tests timed out")
            self.test_results['test_suites']['performance'] = {
                'command': ' '.join(test_command),
                'return_code': -1,
                'error': 'Test timeout after 40 minutes'
            }
    
    def _run_edge_case_tests(self):
        """Run edge case and error scenario tests."""
        logger.info("🔧 Running edge case tests")
        
        test_command = [
            'python', '-m', 'pytest',
            'tests/playwright/test_edge_cases_optimization.py',
            '-v', '--tb=short',
            f'--html={self.output_dir}/reports/edge_cases_report.html',
            '--self-contained-html',
            f'--junitxml={self.output_dir}/reports/edge_cases_junit.xml'
        ]
        
        if self.config['headless']:
            test_command.extend(['--headed=false'])
        
        try:
            result = subprocess.run(
                test_command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            self.test_results['test_suites']['edge_cases'] = {
                'command': ' '.join(test_command),
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }
            
            if result.returncode == 0:
                logger.info("✅ Edge case tests completed successfully")
            else:
                logger.error(f"❌ Edge case tests failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Edge case tests timed out")
            self.test_results['test_suites']['edge_cases'] = {
                'command': ' '.join(test_command),
                'return_code': -1,
                'error': 'Test timeout after 30 minutes'
            }
    
    def _collect_system_metrics(self):
        """Collect system performance metrics."""
        logger.info("📊 Collecting system metrics")
        
        try:
            # Celery Beat task count
            celery_tasks_cmd = [
                'docker-compose', 'exec', '-T', 'web',
                'python', 'manage.py', 'shell', '-c',
                """
from django.conf import settings
print(f'Total Celery Beat tasks: {len(settings.CELERY_BEAT_SCHEDULE)}')
for task_name, config in settings.CELERY_BEAT_SCHEDULE.items():
    print(f'  {task_name}: {config.get("schedule", "N/A")}')
"""
            ]
            
            celery_result = subprocess.run(celery_tasks_cmd, cwd=project_root, capture_output=True, text=True)
            
            # Activity detector health check
            activity_health_cmd = [
                'docker-compose', 'exec', '-T', 'web',
                'python', 'manage.py', 'shell', '-c',
                """
from apps.core.services.session_activity_detector import SimpleSessionActivityDetector
detector = SimpleSessionActivityDetector()
health = detector.health_check()
stats = detector.get_session_statistics()
print(f'Activity detector health: {health}')
print(f'Session statistics: {stats}')
"""
            ]
            
            activity_result = subprocess.run(activity_health_cmd, cwd=project_root, capture_output=True, text=True)
            
            self.test_results['system_metrics'] = {
                'celery_configuration': celery_result.stdout,
                'activity_detector_status': activity_result.stdout,
                'collection_timestamp': datetime.now().isoformat()
            }
            
            logger.info("✅ System metrics collected")
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            self.test_results['errors'].append({
                'type': 'metrics_collection_failure',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    def _validate_optimizations(self):
        """Validate that optimizations are properly implemented."""
        logger.info("✅ Validating optimization implementation")
        
        validation_results = {}
        
        try:
            # Validate Celery Beat schedule optimization
            celery_validation_cmd = [
                'docker-compose', 'exec', '-T', 'web',
                'python', 'manage.py', 'shell', '-c',
                """
from django.conf import settings
schedule = settings.CELERY_BEAT_SCHEDULE

# Count tasks
task_count = len(schedule)
print(f'TASK_COUNT:{task_count}')

# Check unified monitor interval
unified_config = schedule.get('unified-session-monitor', {})
unified_interval = unified_config.get('schedule', 0)
print(f'UNIFIED_INTERVAL:{unified_interval}')

# Check for key optimized tasks
expected_tasks = [
    'unified-session-monitor',
    'monitor-workflow-health',
    'update-session-statistics',
    'cleanup-old-sessions',
    'comprehensive-recovery',
    'warm-active-caches',
    'collect-performance-metrics',
    'cleanup-orphaned-processing',
    'optimize-database-connections'
]

for task in expected_tasks:
    exists = task in schedule
    print(f'TASK_EXISTS:{task}:{exists}')
"""
            ]
            
            celery_validation = subprocess.run(celery_validation_cmd, cwd=project_root, capture_output=True, text=True)
            
            # Parse validation results
            for line in celery_validation.stdout.strip().split('\n'):
                if line.startswith('TASK_COUNT:'):
                    task_count = int(line.split(':')[1])
                    validation_results['celery_task_count'] = task_count
                    validation_results['task_count_optimized'] = task_count <= 12  # Should be ~9 tasks
                    
                elif line.startswith('UNIFIED_INTERVAL:'):
                    interval = float(line.split(':')[1])
                    validation_results['unified_monitor_interval'] = interval
                    validation_results['monitor_interval_optimized'] = interval == 120.0  # Should be 120s
                    
                elif line.startswith('TASK_EXISTS:'):
                    parts = line.split(':')
                    task_name = parts[1]
                    exists = parts[2] == 'True'
                    validation_results[f'task_exists_{task_name.replace("-", "_")}'] = exists
            
            # Validate activity detector configuration
            activity_validation_cmd = [
                'docker-compose', 'exec', '-T', 'web',
                'python', 'manage.py', 'shell', '-c',
                """
from apps.core.services.session_activity_detector import SimpleSessionActivityDetector
detector = SimpleSessionActivityDetector()

# Check monitoring intervals
intervals = detector.MONITORING_INTERVALS
print(f'ACTIVE_INTERVAL:executing:{intervals.get("executing", 0)}')
print(f'ACTIVE_INTERVAL:processing_results:{intervals.get("processing_results", 0)}')
print(f'REVIEW_INTERVAL:ready_for_review:{intervals.get("ready_for_review", 0)}')
print(f'REVIEW_INTERVAL:under_review:{intervals.get("under_review", 0)}')
print(f'DORMANT_INTERVAL:completed:{intervals.get("completed", 0)}')
print(f'DORMANT_INTERVAL:archived:{intervals.get("archived", 0)}')
"""
            ]
            
            activity_validation = subprocess.run(activity_validation_cmd, cwd=project_root, capture_output=True, text=True)
            
            # Parse activity detector results
            expected_intervals = {
                'executing': 60,
                'processing_results': 60,
                'ready_for_review': 600,
                'under_review': 600,
                'completed': 3600,
                'archived': 3600
            }
            
            for line in activity_validation.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 3:
                        _interval_type = parts[0]
                        state = parts[1]
                        interval_value = int(parts[2])
                        
                        validation_results[f'interval_{state}'] = interval_value
                        validation_results[f'interval_{state}_correct'] = interval_value == expected_intervals.get(state, 0)
            
            self.test_results['optimization_validation'] = validation_results
            
            # Overall validation
            critical_validations = [
                validation_results.get('task_count_optimized', False),
                validation_results.get('monitor_interval_optimized', False),
                validation_results.get('interval_executing_correct', False),
                validation_results.get('interval_completed_correct', False)
            ]
            
            self.test_results['optimization_validation']['overall_success'] = all(critical_validations)
            
            if all(critical_validations):
                logger.info("✅ All optimization validations passed")
            else:
                logger.warning(f"⚠️  Some optimization validations failed: {validation_results}")
            
        except Exception as e:
            logger.error(f"Optimization validation failed: {e}")
            self.test_results['errors'].append({
                'type': 'optimization_validation_failure',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    def _generate_reports(self):
        """Generate comprehensive test reports."""
        logger.info("📋 Generating test reports")
        
        try:
            # JSON report
            json_report_path = self.output_dir / 'reports' / 'optimization_test_results.json'
            with open(json_report_path, 'w') as f:
                json.dump(self.test_results, f, indent=2, default=str)
            
            # Markdown summary report
            self._generate_markdown_report()
            
            # HTML dashboard (if requested)
            if self.config['report_format'] in ['html', 'all']:
                self._generate_html_dashboard()
            
            logger.info(f"✅ Reports generated in {self.output_dir}/reports/")
            
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
    
    def _generate_markdown_report(self):
        """Generate markdown summary report."""
        report_path = self.output_dir / 'reports' / 'OPTIMIZATION_TEST_SUMMARY.md'
        
        # Calculate summary statistics
        total_suites = len(self.test_results.get('test_suites', {}))
        successful_suites = len([s for s in self.test_results.get('test_suites', {}).values() if s.get('success', False)])
        
        validation_results = self.test_results.get('optimization_validation', {})
        optimization_success = validation_results.get('overall_success', False)
        
        report_content = f"""# Optimization Validation Test Report

## Executive Summary

**Test Date:** {self.test_results['start_time']}  
**Duration:** {self.test_results.get('duration_seconds', 0):.2f} seconds  
**Test Configuration:** {self.config['test_type']}  

### Results Overview

- **Test Suites:** {successful_suites}/{total_suites} passed
- **Optimization Validation:** {'✅ PASSED' if optimization_success else '❌ FAILED'}
- **Critical Issues:** {len(self.test_results.get('errors', []))}

## Optimization Implementation Status

### Phase 1: CELERY_BEAT_SCHEDULE Optimization
- **Task Count Reduction:** {validation_results.get('celery_task_count', 'N/A')} tasks (Target: ≤12)
- **Task Count Optimized:** {'✅' if validation_results.get('task_count_optimized') else '❌'}

### Phase 2: Unified Monitoring Frequency
- **Monitoring Interval:** {validation_results.get('unified_monitor_interval', 'N/A')}s (Target: 120s)
- **Interval Optimized:** {'✅' if validation_results.get('monitor_interval_optimized') else '❌'}

### Phase 3: Activity-Based Monitoring Intervals
- **Active States (executing):** {validation_results.get('interval_executing', 'N/A')}s {'✅' if validation_results.get('interval_executing_correct') else '❌'}
- **Review States (ready_for_review):** {validation_results.get('interval_ready_for_review', 'N/A')}s {'✅' if validation_results.get('interval_ready_for_review_correct') else '❌'}
- **Dormant States (completed):** {validation_results.get('interval_completed', 'N/A')}s {'✅' if validation_results.get('interval_completed_correct') else '❌'}

## Test Suite Results

"""
        
        # Add test suite details
        for suite_name, suite_results in self.test_results.get('test_suites', {}).items():
            status = '✅ PASSED' if suite_results.get('success') else '❌ FAILED'
            report_content += f"### {suite_name.replace('_', ' ').title()}\n"
            report_content += f"**Status:** {status}  \n"
            report_content += f"**Return Code:** {suite_results.get('return_code', 'N/A')}  \n\n"
        
        report_content += f"""
## Performance Metrics

{self._format_performance_metrics()}

## Error Analysis

{self._format_error_analysis()}

## Recommendations

{self._generate_recommendations()}

---

*Generated on {datetime.now().isoformat()} by Optimization Test Runner*
"""
        
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        logger.info(f"📋 Markdown report generated: {report_path}")
    
    def _format_performance_metrics(self):
        """Format performance metrics for the report."""
        # This would parse performance data from test results
        # For now, provide placeholder
        return """
Performance metrics will be extracted from test execution logs and Playwright reports.
Key metrics include:
- Page load times across different session states
- API response times during optimization
- UI responsiveness during background monitoring
- System resource usage patterns
"""
    
    def _format_error_analysis(self):
        """Format error analysis for the report."""
        errors = self.test_results.get('errors', [])
        if not errors:
            return "No critical errors detected during testing."
        
        error_analysis = f"**Total Errors:** {len(errors)}\n\n"
        
        error_types = {}
        for error in errors:
            error_type = error.get('type', 'unknown')
            if error_type not in error_types:
                error_types[error_type] = []
            error_types[error_type].append(error)
        
        for error_type, error_list in error_types.items():
            error_analysis += f"**{error_type}:** {len(error_list)} occurrences\n"
            for error in error_list[:3]:  # Show first 3 errors
                error_analysis += f"  - {error.get('message', 'No message')}\n"
            if len(error_list) > 3:
                error_analysis += f"  - ... and {len(error_list) - 3} more\n"
            error_analysis += "\n"
        
        return error_analysis
    
    def _generate_recommendations(self):
        """Generate recommendations based on test results."""
        recommendations = []
        
        validation = self.test_results.get('optimization_validation', {})
        
        if not validation.get('task_count_optimized'):
            recommendations.append("🔄 Review CELERY_BEAT_SCHEDULE - task count may be higher than expected")
        
        if not validation.get('monitor_interval_optimized'):
            recommendations.append("⏰ Verify unified monitoring interval is set to 120 seconds")
        
        if not validation.get('interval_executing_correct'):
            recommendations.append("🎯 Check activity detector intervals for executing state (should be 60s)")
        
        errors = self.test_results.get('errors', [])
        if len(errors) > 5:
            recommendations.append(f"🐛 High error count ({len(errors)}) - investigate test failures")
        
        suite_failures = [name for name, results in self.test_results.get('test_suites', {}).items() 
                         if not results.get('success')]
        if suite_failures:
            recommendations.append(f"🧪 Test suite failures: {', '.join(suite_failures)}")
        
        if not recommendations:
            recommendations.append("✨ All optimizations validated successfully - no immediate actions required")
        
        return '\n'.join([f"- {rec}" for rec in recommendations])
    
    def _generate_html_dashboard(self):
        """Generate HTML dashboard for test results."""
        # This would create an interactive HTML dashboard
        # For now, create a simple HTML file
        html_path = self.output_dir / 'reports' / 'optimization_dashboard.html'
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Optimization Test Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .success {{ color: green; }}
        .failure {{ color: red; }}
        .warning {{ color: orange; }}
        .metric {{ background: #f5f5f5; padding: 10px; margin: 5px 0; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Optimization Validation Dashboard</h1>
    
    <h2>Test Overview</h2>
    <div class="metric">
        <strong>Test Date:</strong> {self.test_results['start_time']}<br>
        <strong>Duration:</strong> {self.test_results.get('duration_seconds', 0):.2f} seconds<br>
        <strong>Configuration:</strong> {self.config}
    </div>
    
    <h2>Optimization Status</h2>
    <div class="metric">
        <strong>Overall Success:</strong> 
        <span class="{'success' if self.test_results.get('optimization_validation', {}).get('overall_success') else 'failure'}">
            {'PASSED' if self.test_results.get('optimization_validation', {}).get('overall_success') else 'FAILED'}
        </span>
    </div>
    
    <h2>Test Results</h2>
    <pre>{json.dumps(self.test_results, indent=2, default=str)}</pre>
    
</body>
</html>
"""
        
        with open(html_path, 'w') as f:
            f.write(html_content)
        
        logger.info(f"📊 HTML dashboard generated: {html_path}")
    
    def _cleanup_test_environment(self):
        """Clean up test environment after test run."""
        logger.info("🧹 Cleaning up test environment")
        
        try:
            # Keep services running for inspection if requested
            if not self.config.get('cleanup', True):
                logger.info("⏸️  Skipping cleanup - services left running for inspection")
                return
            
            # Optional: Stop services
            # subprocess.run(['docker-compose', 'down'], cwd=project_root)
            
            logger.info("✅ Test environment cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


def main():
    """Main entry point for optimization test runner."""
    parser = argparse.ArgumentParser(
        description="Run comprehensive optimization validation tests",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--test-type', 
        choices=['all', 'user-journey', 'performance', 'edge-cases'],
        default='all',
        help='Type of tests to run (default: all)'
    )
    
    parser.add_argument(
        '--report-format',
        choices=['json', 'markdown', 'html', 'all'],
        default='all',
        help='Output report format (default: all)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./test_results',
        help='Directory for test results and reports (default: ./test_results)'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser tests in headless mode'
    )
    
    parser.add_argument(
        '--parallel',
        type=int,
        default=1,
        help='Number of parallel test processes (default: 1)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Skip cleanup - leave services running for inspection'
    )
    
    args = parser.parse_args()
    
    config = {
        'test_type': args.test_type,
        'report_format': args.report_format,
        'output_dir': args.output_dir,
        'headless': args.headless,
        'parallel': args.parallel,
        'verbose': args.verbose,
        'cleanup': not args.no_cleanup
    }
    
    # Initialize and run tests
    runner = OptimizationTestRunner(config)
    results = runner.run_optimization_tests()
    
    # Print summary
    print("\n" + "="*50)
    print("OPTIMIZATION TEST SUMMARY")
    print("="*50)
    
    validation = results.get('optimization_validation', {})
    overall_success = validation.get('overall_success', False)
    
    print(f"Overall Status: {'✅ PASSED' if overall_success else '❌ FAILED'}")
    print(f"Duration: {results.get('duration_seconds', 0):.2f} seconds")
    print(f"Error Count: {len(results.get('errors', []))}")
    
    print(f"\nReports generated in: {config['output_dir']}/reports/")
    
    # Exit with appropriate code
    sys.exit(0 if overall_success and len(results.get('errors', [])) == 0 else 1)


if __name__ == "__main__":
    main()