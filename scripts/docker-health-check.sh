#!/bin/bash
# Docker Health Check Script
# Diagnoses common Docker and container issues in Agent Grey
# See: docs/docker/DOCKER-TROUBLESHOOTING.md

set -e

echo "======================================================"
echo "  Agent Grey - Docker Health Check"
echo "======================================================"
echo ""

echo "=== Docker System Status ==="
docker system df
echo ""

echo "=== Container Status ==="
docker-compose ps
echo ""

echo "=== Unhealthy Containers ==="
unhealthy=$(docker-compose ps | grep -i "unhealthy" || echo "None")
if [ "$unhealthy" = "None" ]; then
    echo "✅ All containers are healthy"
else
    echo "⚠️  Found unhealthy containers:"
    echo "$unhealthy"
fi
echo ""

echo "=== Recent Errors (last 5 minutes) ==="
errors=$(docker-compose logs --tail=20 --since=5m 2>&1 | grep -i "error" || echo "No errors found")
if [ "$errors" = "No errors found" ]; then
    echo "✅ No recent errors"
else
    echo "⚠️  Recent errors found:"
    echo "$errors"
fi
echo ""

echo "=== Database Connection ==="
db_status=$(docker-compose exec -T db psql -U thesis_grey_user -d thesis_grey_dev_db -c "SELECT 1;" 2>&1 || echo "Failed")
if [[ "$db_status" == *"Failed"* ]]; then
    echo "❌ Database connection failed"
else
    echo "✅ Database connection successful"
fi
echo ""

echo "=== Redis Connection ==="
redis_status=$(docker-compose exec -T redis redis-cli ping 2>&1 || echo "Failed")
if [[ "$redis_status" == *"PONG"* ]]; then
    echo "✅ Redis connection successful"
else
    echo "❌ Redis connection failed: $redis_status"
fi
echo ""

echo "=== Web Service Health ==="
web_health=$(curl -s http://localhost:8000/health/ 2>&1 || echo "Failed")
if [[ "$web_health" == *"Failed"* ]]; then
    echo "❌ Web service not responding"
else
    echo "✅ Web service healthy"
    echo "$web_health" | head -5
fi
echo ""

echo "=== Disk Usage ==="
df -h | grep -E "Filesystem|docker" || df -h | head -2
echo ""

echo "======================================================"
echo "  Health Check Complete"
echo "======================================================"
echo ""
echo "For detailed troubleshooting, see:"
echo "  docs/docker/DOCKER-TROUBLESHOOTING.md"
echo ""
