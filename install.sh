#!/bin/bash

# Agent Grey - Easy Install Script
# This script sets up Agent Grey for non-developers
# Requirements: Docker and Docker Compose

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "${BLUE}"
    echo "=================================================="
    echo "🚀 Agent Grey - Easy Installation"
    echo "=================================================="
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check system requirements
check_requirements() {
    print_info "Checking system requirements..."
    
    # Check Docker
    if command_exists docker; then
        print_success "Docker is installed"
        
        # Check if Docker daemon is running
        if ! docker info >/dev/null 2>&1; then
            print_error "Docker is installed but not running. Please start Docker and try again."
            exit 1
        fi
    else
        print_error "Docker is not installed."
        echo "Please install Docker from: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # Check Docker Compose
    if command_exists docker-compose || docker compose version >/dev/null 2>&1; then
        print_success "Docker Compose is available"
    else
        print_error "Docker Compose is not available."
        echo "Please install Docker Compose or use a newer version of Docker that includes Compose V2"
        exit 1
    fi
}

# Set up environment file
setup_environment() {
    print_info "Setting up environment configuration..."
    
    if [ ! -f ".env.example" ]; then
        print_error ".env.example file not found. Please ensure all files are downloaded correctly."
        exit 1
    fi
    
    if [ ! -f ".env.local" ]; then
        cp .env.example .env.local
        print_success "Created .env.local from template"
    else
        print_warning ".env.local already exists, skipping creation"
    fi
    
    # Check if SERPER_API_KEY is set
    if ! grep -q "^SERPER_API_KEY=.\+" .env.local 2>/dev/null; then
        print_warning "SERPER_API_KEY not configured in .env.local"
        echo
        echo "Agent Grey requires a Serper API key for search functionality."
        echo "Get your free API key at: https://serper.dev/"
        echo
        read -p "Enter your Serper API key (or press Enter to configure later): " api_key
        
        if [ -n "$api_key" ]; then
            # Update or add the API key
            if grep -q "^SERPER_API_KEY=" .env.local; then
                sed -i "s/^SERPER_API_KEY=.*/SERPER_API_KEY=$api_key/" .env.local
            else
                echo "SERPER_API_KEY=$api_key" >> .env.local
            fi
            print_success "API key configured"
        else
            print_warning "API key not configured. You can add it later to .env.local"
        fi
    else
        print_success "SERPER_API_KEY is already configured"
    fi
}

# Pull Docker images
pull_images() {
    print_info "Pulling Docker images (this may take a few minutes)..."
    
    # Determine which docker-compose command to use
    COMPOSE_CMD="docker-compose"
    if ! command_exists docker-compose && docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    fi
    
    # Check if docker-compose.production.yml exists
    if [ ! -f "docker-compose.production.yml" ]; then
        print_error "docker-compose.production.yml not found. Please ensure all files are downloaded correctly."
        exit 1
    fi
    
    $COMPOSE_CMD -f docker-compose.production.yml pull
    print_success "Docker images downloaded"
}

# Start services
start_services() {
    print_info "Starting Agent Grey services..."
    
    # Determine which docker-compose command to use
    COMPOSE_CMD="docker-compose"
    if ! command_exists docker-compose && docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    fi
    
    $COMPOSE_CMD -f docker-compose.production.yml up -d
    
    print_info "Waiting for services to start up..."
    sleep 10
    
    # Check if web service is healthy
    for i in {1..30}; do
        if curl -f http://localhost:8000/health/ >/dev/null 2>&1; then
            print_success "Agent Grey is running!"
            break
        fi
        echo -n "."
        sleep 2
        if [ $i -eq 30 ]; then
            print_warning "Services are starting but may not be ready yet. Check with 'docker-compose -f docker-compose.production.yml logs'"
        fi
    done
}

# Print final instructions
print_final_instructions() {
    echo
    echo -e "${GREEN}"
    echo "=================================================="
    echo "🎉 Agent Grey Installation Complete!"
    echo "=================================================="
    echo -e "${NC}"
    echo
    echo "🌐 Access Agent Grey at: http://localhost:8000"
    echo "👤 Default admin login: admin / admin123"
    echo
    echo "📋 Useful commands:"
    echo "  View logs:    docker-compose -f docker-compose.production.yml logs -f"
    echo "  Stop:         docker-compose -f docker-compose.production.yml down"
    echo "  Restart:      docker-compose -f docker-compose.production.yml restart"
    echo "  Update:       docker-compose -f docker-compose.production.yml pull && docker-compose -f docker-compose.production.yml up -d"
    echo
    echo "📚 Documentation: https://github.com/your-repo/agent-grey"
    echo "🐛 Issues: https://github.com/your-repo/agent-grey/issues"
    echo
    if ! grep -q "^SERPER_API_KEY=.\+" .env.local 2>/dev/null; then
        print_warning "Remember to add your SERPER_API_KEY to .env.local for search functionality!"
    fi
}

# Main installation process
main() {
    print_header
    
    echo "This script will install and start Agent Grey on your system."
    echo "Requirements: Docker and Docker Compose"
    echo
    read -p "Continue with installation? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    
    check_requirements
    setup_environment
    pull_images
    start_services
    print_final_instructions
}

# Handle Ctrl+C
trap 'echo -e "\n${RED}Installation interrupted by user${NC}"; exit 1' INT

# Run main function
main "$@"