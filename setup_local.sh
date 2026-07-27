#!/bin/bash
# FiscAudit AI - Local Development Setup Script
# Run this to set up everything for local development

set -e

echo "🚀 FiscAudit AI - Local Setup"
echo "════════════════════════════════════════════"
echo ""

# Check Python version
echo "1️⃣ Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3.11+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✅ Python $PYTHON_VERSION found"
echo ""

# Create virtual environment
echo "2️⃣ Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "3️⃣ Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Upgrade pip
echo "4️⃣ Upgrading pip..."
pip install --upgrade pip setuptools wheel --quiet
echo "✅ Pip upgraded"
echo ""

# Install requirements
echo "5️⃣ Installing dependencies..."
pip install -r requirements.txt --quiet
echo "✅ Dependencies installed"
echo ""

# Create .streamlit directory
echo "6️⃣ Setting up Streamlit configuration..."
mkdir -p .streamlit
echo "✅ .streamlit directory created"
echo ""

# Copy secrets template if not exists
if [ ! -f ".streamlit/secrets.toml" ]; then
    echo "7️⃣ Creating secrets.toml template..."
    cp .streamlit/secrets.toml.example .streamlit/secrets.toml
    echo "⚠️  secrets.toml created from template"
    echo "   ⚡ IMPORTANT: Edit .streamlit/secrets.toml and add your API keys!"
    echo ""
else
    echo "7️⃣ secrets.toml already exists"
    echo ""
fi

# Check if secrets are configured
echo "8️⃣ Checking API configuration..."
if grep -q "your-" .streamlit/secrets.toml; then
    echo "⚠️  API keys not yet configured!"
    echo ""
    echo "   Next steps:"
    echo "   1. Edit .streamlit/secrets.toml"
    echo "   2. Add your API keys:"
    echo "      • Google Gemini: https://makersuite.google.com/"
    echo "      • Anthropic Claude: https://console.anthropic.com/"
    echo "      • Supabase: https://supabase.com/dashboard"
    echo ""
else
    echo "✅ API keys configured!"
fi

echo ""
echo "════════════════════════════════════════════"
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Configure API keys (if not done):"
echo "      nano .streamlit/secrets.toml"
echo ""
echo "   2. Run the app:"
echo "      streamlit run app.py"
echo ""
echo "   3. Open in browser:"
echo "      http://localhost:8501"
echo ""
echo "📚 Documentation:"
echo "   • STREAMLIT_CLOUD_DEPLOYMENT.md - Deployment guide"
echo "   • DESIGN_SYSTEM.md - Design specifications"
echo "   • CODE_REVIEW_REPORT.md - Code quality analysis"
echo ""
echo "🚀 Ready to run FiscAudit AI!"
