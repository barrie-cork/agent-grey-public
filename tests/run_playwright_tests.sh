#!/bin/bash
# Agent Grey Playwright Test Runner
# This script sets up and runs Playwright end-to-end tests

set -e  # Exit on any error

echo "🎭 Agent Grey Playwright Test Runner"
echo "===================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
HEADLESS=true
RECORD_VIDEO=false
RECORD_HAR=false
TEST_PATTERN="tests/playwright/"
BROWSER="chromium"
WORKERS=1

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --headed)
            HEADLESS=false
            shift
            ;;
        --video)
            RECORD_VIDEO=true
            shift
            ;;
        --har)
            RECORD_HAR=true
            shift
            ;;
        --browser)
            BROWSER="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --pattern)
            TEST_PATTERN="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --headed          Run in headed mode (show browser)"
            echo "  --video           Record videos of test runs"
            echo "  --har             Record network traffic"
            echo "  --browser BROWSER Browser to use (chromium, firefox, webkit)"
            echo "  --workers N       Number of parallel workers"
            echo "  --pattern PATTERN Test pattern to run"
            echo "  --help            Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # Run all tests headless"
            echo "  $0 --headed                    # Run with browser visible"
            echo "  $0 --video --har               # Record video and network traffic"
            echo "  $0 --pattern test_workflow.py  # Run specific test file"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check if we're in Docker or local environment
if [ -f /.dockerenv ]; then
    ENVIRONMENT="docker"
    DJANGO_COMMAND="python manage.py"
else
    ENVIRONMENT="local"
    DJANGO_COMMAND="docker-compose exec web python manage.py"
fi

echo -e "${BLUE}Environment: $ENVIRONMENT${NC}"
echo -e "${BLUE}Headless: $HEADLESS${NC}"
echo -e "${BLUE}Browser: $BROWSER${NC}"
echo -e "${BLUE}Workers: $WORKERS${NC}"
echo -e "${BLUE}Test Pattern: $TEST_PATTERN${NC}"
echo ""

# Function to check if Django server is running
check_django_server() {
    local url="http://localhost:8000/health/"
    local timeout=30
    local count=0
    
    echo -e "${YELLOW}Checking if Django server is running...${NC}"
    
    while [ $count -lt $timeout ]; do
        if curl -s --max-time 5 "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Django server is running${NC}"
            return 0
        fi
        count=$((count + 1))
        sleep 1
    done
    
    echo -e "${RED}✗ Django server is not responding${NC}"
    return 1
}

# Function to start Django server if needed
start_django_server() {
    if [ "$ENVIRONMENT" = "docker" ]; then
        echo -e "${YELLOW}Starting Django server in Docker...${NC}"
        docker-compose up -d web
        sleep 10
    else
        echo -e "${YELLOW}Please ensure Django server is running:${NC}"
        echo "  docker-compose up -d"
        echo "  OR"
        echo "  python manage.py runserver"
    fi
}

# Function to install Playwright browsers
install_playwright_browsers() {
    echo -e "${YELLOW}Installing Playwright browsers...${NC}"
    
    if [ "$ENVIRONMENT" = "docker" ]; then
        docker-compose exec web playwright install $BROWSER
        docker-compose exec web playwright install-deps
    else
        playwright install $BROWSER
        playwright install-deps
    fi
}

# Function to run database migrations
run_migrations() {
    echo -e "${YELLOW}Running database migrations...${NC}"
    $DJANGO_COMMAND migrate --run-syncdb
}

# Function to create test user
create_test_user() {
    echo -e "${YELLOW}Creating test user...${NC}"
    $DJANGO_COMMAND shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='testuser').exists():
    User.objects.create_user('testuser', 'test@example.com', 'testpass123')
    print('Test user created')
else:
    print('Test user already exists')
"
}

# Function to run the actual tests
run_tests() {
    echo -e "${YELLOW}Running Playwright tests...${NC}"
    
    # Set environment variables
    export HEADLESS=$HEADLESS
    export RECORD_VIDEO=$RECORD_VIDEO
    export RECORD_HAR=$RECORD_HAR
    export PLAYWRIGHT_BROWSER=$BROWSER
    
    # Create directories for recordings if needed
    if [ "$RECORD_VIDEO" = true ]; then
        mkdir -p tests/playwright/videos
    fi
    
    if [ "$RECORD_HAR" = true ]; then
        mkdir -p tests/playwright/har
    fi
    
    # Playwright test command
    local pytest_cmd="pytest"
    pytest_cmd="$pytest_cmd $TEST_PATTERN"
    pytest_cmd="$pytest_cmd -v"
    pytest_cmd="$pytest_cmd --tb=short"
    pytest_cmd="$pytest_cmd -x"  # Stop on first failure
    
    if [ "$WORKERS" -gt 1 ]; then
        pytest_cmd="$pytest_cmd -n $WORKERS"
    fi
    
    # Add markers
    pytest_cmd="$pytest_cmd -m playwright"
    
    # Run the tests
    if [ "$ENVIRONMENT" = "docker" ]; then
        docker-compose exec web $pytest_cmd
    else
        $pytest_cmd
    fi
}

# Function to generate test report
generate_report() {
    echo -e "${YELLOW}Generating test report...${NC}"
    
    local report_cmd="pytest --html=tests/playwright/reports/report.html --self-contained-html $TEST_PATTERN -m playwright --tb=short"
    
    mkdir -p tests/playwright/reports
    
    if [ "$ENVIRONMENT" = "docker" ]; then
        docker-compose exec web $report_cmd
    else
        $report_cmd
    fi
    
    echo -e "${GREEN}Test report generated: tests/playwright/reports/report.html${NC}"
}

# Main execution
main() {
    echo -e "${BLUE}Step 1: Checking prerequisites...${NC}"
    
    # Check if Django server is running, start if needed
    if ! check_django_server; then
        start_django_server
        sleep 5
        if ! check_django_server; then
            echo -e "${RED}Failed to start Django server${NC}"
            exit 1
        fi
    fi
    
    echo -e "${BLUE}Step 2: Installing Playwright browsers...${NC}"
    install_playwright_browsers
    
    echo -e "${BLUE}Step 3: Setting up database...${NC}"
    run_migrations
    create_test_user
    
    echo -e "${BLUE}Step 4: Running tests...${NC}"
    if run_tests; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        
        echo -e "${BLUE}Step 5: Generating report...${NC}"
        generate_report
        
        echo -e "${GREEN}🎉 Test run completed successfully!${NC}"
        
        # Show additional information
        if [ "$RECORD_VIDEO" = true ]; then
            echo -e "${BLUE}Videos recorded in: tests/playwright/videos/${NC}"
        fi
        
        if [ "$RECORD_HAR" = true ]; then
            echo -e "${BLUE}Network traces in: tests/playwright/har/${NC}"
        fi
        
    else
        echo -e "${RED}✗ Some tests failed${NC}"
        
        # Generate failure report
        generate_report
        
        echo -e "${YELLOW}Check the test report for details: tests/playwright/reports/report.html${NC}"
        exit 1
    fi
}

# Trap to cleanup on exit
cleanup() {
    echo -e "${YELLOW}Cleaning up...${NC}"
    
    # Clean up any temporary files or processes if needed
    # For now, just show completion message
    echo -e "${BLUE}Cleanup completed${NC}"
}

trap cleanup EXIT

# Run main function
main "$@"