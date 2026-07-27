#!/bin/bash

# =============================================================================
# FiscAudit AI - GitHub Push Script
# =============================================================================
# Dit script pusht de volledige applicatie naar je GitHub repository
# 
# STAP 1: Clone je repository EERST
# STAP 2: Voer dit script uit
# 
# =============================================================================

set -e  # Stop on error

echo "🚀 FiscAudit AI - GitHub Push Workflow"
echo "======================================"
echo ""

# =============================================================================
# STAP 1: GEBRUIKER INPUT
# =============================================================================

echo "📝 Stap 1: Repository Informatie"
echo "--------------------------------"

# Check of .git bestaat
if [ ! -d ".git" ]; then
    echo "❌ Fout: Dit is geen Git repository"
    echo "   Run eerst: git clone https://github.com/YOUR_USERNAME/Fiscale-audit.git"
    exit 1
fi

# Repository URL
REPO_URL="${1:-https://github.com/patrickdereuver98-lab/Fiscale-audit.git}"

echo "📚 Repository URL: $REPO_URL"
echo ""

# =============================================================================
# STAP 2: BRANCH SETUP
# =============================================================================

echo "📌 Stap 2: Branch Setup"
echo "------------------------"

# Rename master naar main (als nodig)
if git rev-parse --verify main >/dev/null 2>&1; then
    echo "✓ Branch 'main' bestaat al"
    git checkout main
else
    echo "⚠ Branch 'main' bestaat niet, probeer 'master'..."
    if git rev-parse --verify master >/dev/null 2>&1; then
        echo "  Renaming 'master' → 'main'"
        git branch -m master main || true
    fi
fi

echo ""

# =============================================================================
# STAP 3: REMOTE TOEVOEGEN
# =============================================================================

echo "🔗 Stap 3: Remote Repository"
echo "-----------------------------"

# Check of remote 'origin' al bestaat
if git remote get-url origin >/dev/null 2>&1; then
    CURRENT_REMOTE=$(git remote get-url origin)
    if [ "$CURRENT_REMOTE" = "$REPO_URL" ]; then
        echo "✓ Remote 'origin' is correct geconfigureerd"
    else
        echo "⚠ Remote 'origin' wijst naar: $CURRENT_REMOTE"
        echo "  Update naar: $REPO_URL"
        git remote set-url origin "$REPO_URL"
        echo "✓ Remote updated"
    fi
else
    echo "→ Remote 'origin' toevoegen..."
    git remote add origin "$REPO_URL"
    echo "✓ Remote toegevoegd"
fi

echo ""

# =============================================================================
# STAP 4: CREDENTIALS SETUP
# =============================================================================

echo "🔐 Stap 4: Authenticatie Check"
echo "-------------------------------"

# Test connectie
echo "→ Testen GitHub connectie..."
if git ls-remote origin HEAD >/dev/null 2>&1; then
    echo "✓ GitHub connectie OK"
else
    echo "⚠ Kan niet connecteren met GitHub"
    echo "  Mogelijke oorzaken:"
    echo "  1. Je bent niet ingelogd op GitHub CLI (github-cli)"
    echo "  2. Je SSH keys zijn niet geconfigureerd"
    echo "  3. Je internet connectie is weg"
    echo ""
    echo "  OPLOSSINGEN:"
    echo "  A) GitHub CLI setup (aanbevolen):"
    echo "     $ gh auth login"
    echo ""
    echo "  B) SSH keys setup:"
    echo "     $ ssh-keygen -t ed25519"
    echo "     $ cat ~/.ssh/id_ed25519.pub"
    echo "     (Voeg toe op: https://github.com/settings/keys)"
    echo ""
    echo "  C) Personal Access Token (PAT):"
    echo "     $ git credential fill"
    echo "     (Vul je GitHub username + PAT in)"
    exit 1
fi

echo ""

# =============================================================================
# STAP 5: PRE-PUSH CHECKS
# =============================================================================

echo "✅ Stap 5: Pre-Push Checks"
echo "----------------------------"

# Check uncommitted changes
UNCOMMITTED=$(git status --porcelain | wc -l)
if [ "$UNCOMMITTED" -gt 0 ]; then
    echo "⚠ Er zijn uncommitted changes:"
    git status --short
    echo ""
    read -p "  Commit nu? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git add -A
        git commit -m "📝 Work in progress - Auto commit before push"
    else
        echo "→ Skipping push"
        exit 1
    fi
fi

# Check commits
COMMITS=$(git rev-list --count origin/main..main 2>/dev/null || echo "0")
echo "✓ Commits to push: $COMMITS"

# Check branch tracking
if git rev-parse --verify origin/main >/dev/null 2>&1; then
    echo "✓ Remote branch exists"
else
    echo "ℹ Remote branch 'main' doesn't exist yet (first push)"
fi

echo ""

# =============================================================================
# STAP 6: PUSH NAAR GITHUB
# =============================================================================

echo "📤 Stap 6: Push naar GitHub"
echo "----------------------------"

echo "→ Pushing branch 'main' naar origin..."
if git push -u origin main; then
    echo "✅ Push succesvol!"
else
    echo "❌ Push failed"
    exit 1
fi

echo ""

# =============================================================================
# STAP 7: VERIFICATIE
# =============================================================================

echo "🔍 Stap 7: Verificatie"
echo "---------------------"

# Haal latest info
git fetch origin

# Check status
if git rev-parse --verify origin/main >/dev/null 2>&1; then
    echo "✓ Remote branch 'main' is nu beschikbaar"
    
    # Vergelijk commits
    LOCAL_COMMIT=$(git rev-parse main)
    REMOTE_COMMIT=$(git rev-parse origin/main)
    
    if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
        echo "✓ Local en remote zijn in sync"
    else
        echo "⚠ Local en remote verschillen"
    fi
fi

echo ""

# =============================================================================
# SUMMARY
# =============================================================================

echo "🎉 Push Compleet!"
echo "=================="
echo ""
echo "📊 Repository Details:"
echo "  URL: $REPO_URL"
echo "  Branch: main"
echo "  Status: ✓ Up to date"
echo ""
echo "📁 Wat is geüpload:"
echo "  • app.py (Streamlit applicatie)"
echo "  • src/ (5 Python modules)"
echo "  • schema.sql (Supabase database)"
echo "  • requirements.txt (Dependencies)"
echo "  • .streamlit/ (Config + secrets template)"
echo "  • README.md (Documentatie)"
echo "  • .gitignore (Git ignore rules)"
echo ""
echo "🔗 Je repository:"
echo "  https://github.com/patrickdereuver98-lab/Fiscale-audit"
echo ""
echo "⏭️  Volgende stappen:"
echo "  1. ✓ GitHub repository setup compleet"
echo "  2. → Supabase database setup (zie README.md)"
echo "  3. → Configureer API keys (.streamlit/secrets.toml)"
echo "  4. → Test lokaal: streamlit run app.py"
echo "  5. → Deploy op Streamlit Cloud (optioneel)"
echo ""
