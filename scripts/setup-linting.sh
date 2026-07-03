#!/bin/bash
# Setup script for flake8 linting in Agent Grey
set -e

echo "🔧 Agent Grey - Linting Setup"
echo "=============================="
echo ""

# Check if we're in the right directory
if [ ! -f ".flake8" ]; then
    echo "❌ Error: .flake8 not found. Please run this script from the project root."
    exit 1
fi

# Check Python availability
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found. Please install Python 3.12+"
    exit 1
fi

echo "✅ Project root detected"
echo ""

# Install flake8
echo "📦 Installing flake8..."
if [ -d "venv" ]; then
    echo "   Using existing virtualenv: venv/"
    source venv/bin/activate
    pip install -q flake8 black isort pre-commit
elif docker-compose ps web &> /dev/null; then
    echo "   Using Docker environment"
    docker-compose exec -T web pip install -q flake8 black isort pre-commit
else
    echo "   Installing globally (consider using virtualenv)"
    pip install --user -q flake8 black isort pre-commit
fi
echo "✅ Flake8 installed"
echo ""

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    echo "✅ Pre-commit hooks installed"
else
    echo "⚠️  pre-commit not in PATH, skipping hook installation"
    echo "   Install manually with: pip install pre-commit && pre-commit install"
fi
echo ""

# Test flake8 configuration
echo "🧪 Testing flake8 configuration..."
if flake8 --version &> /dev/null; then
    echo "✅ Flake8 is working"
    echo ""
    echo "Running sample check..."
    flake8 apps/core/logging_config.py && echo "   ✅ No issues found" || echo "   ⚠️  Issues detected (this is normal)"
else
    echo "⚠️  Could not verify flake8 installation"
fi
echo ""

# IDE-specific instructions
echo "📝 Next Steps:"
echo ""
echo "1. Configure your IDE:"
echo "   - VS Code: Already configured in .vscode/settings.json"
echo "   - PyCharm: See docs/IDE_SETUP.md"
echo "   - Other IDEs: See docs/IDE_SETUP.md"
echo ""
echo "2. Test pre-commit hooks:"
echo "   git commit --allow-empty -m 'test hooks'"
echo ""
echo "3. Run full flake8 check:"
echo "   flake8"
echo ""
echo "4. For manual quality checks:"
echo "   pre-commit run --all-files --hook-stage manual"
echo ""
echo "✨ Setup complete! Happy coding!"
