# 🚀 FiscAudit AI - Streamlit Cloud Deployment Guide

Complete guide for deploying to Streamlit Cloud (and traditional servers)

---

## ✅ PRE-DEPLOYMENT CHECKLIST

Before deploying, ensure you have:

- [ ] GitHub account with repository pushed
- [ ] Streamlit account (https://streamlit.io/)
- [ ] Google Gemini API key (https://makersuite.google.com/)
- [ ] Anthropic Claude API key (https://console.anthropic.com/)
- [ ] Supabase account & project (https://supabase.com/)
- [ ] Fixed `requirements.txt` (no problematic dependencies)
- [ ] `.streamlit/config.toml` configured
- [ ] `.streamlit/secrets.toml.example` template prepared

---

## 🐛 FIX #1: Requirements.txt Issues

### Problem
The original requirements.txt had this invalid dependency:
```
streamlit-aggrid==0.3.5.post2  ❌ Version doesn't exist!
```

### Solution
✅ Updated to flexible versions:
```
streamlit>=1.32.0,<2.0        ✅ Latest stable
google-generativeai>=0.3.0     ✅ Flexible versions
anthropic>=0.8.0               ✅ No yanked versions
```

### Verify
```bash
pip install -r requirements.txt
```

Should complete without errors ✅

---

## 🔧 FIX #2: Streamlit Configuration

### What was missing:
- `.streamlit/config.toml` - Streamlit settings
- `.streamlit/secrets.toml` - API keys configuration

### What we added:

#### `.streamlit/config.toml`
```toml
[theme]
primaryColor = "#2563EB"
backgroundColor = "#0F172A"
secondaryBackgroundColor = "#1E293B"
textColor = "#F8FAFC"
```
✅ Professional dark theme applied automatically

#### `.streamlit/secrets.toml.example`
Template showing required secrets:
```toml
google_api_key = "your-key-here"
anthropic_api_key = "your-key-here"
supabase_url = "your-url-here"
supabase_key = "your-key-here"
```

---

## 🌐 DEPLOYMENT OPTIONS

### Option A: Streamlit Cloud (Recommended for Quick Start)

#### Step 1: Push Code to GitHub
```bash
cd fiscale-audit
git add .
git commit -m "Production ready"
git push origin main
```

#### Step 2: Connect Streamlit Cloud
1. Go to https://share.streamlit.io/
2. Click "Create app"
3. Connect GitHub repository
4. Select: `patrickdereuver98-lab/Fiscale-audit`
5. Select branch: `main`
6. Select file: `app.py`
7. Click "Deploy"

#### Step 3: Add Secrets to Streamlit Cloud
1. Go to app dashboard
2. Click "⋮" (three dots) → Settings
3. Click "Secrets" in sidebar
4. Paste your secrets (copy from secrets.toml):
```toml
google_api_key = "your-actual-key"
anthropic_api_key = "your-actual-key"
supabase_url = "your-actual-url"
supabase_key = "your-actual-key"
environment = "production"
debug = false
```
5. Click "Save"

#### Step 4: Done! 🎉
Your app is live at: `https://fiscale-audit-yourname.streamlit.app/`

---

### Option B: Docker Deployment

#### Step 1: Create Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .
COPY src/ ./src/
COPY assets/ ./assets/

# Create .streamlit directory
RUN mkdir -p .streamlit
COPY .streamlit/config.toml .streamlit/

# Expose port
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.headless=true"]
```

#### Step 2: Build Image
```bash
docker build -t fiscaudit-ai:latest .
```

#### Step 3: Run Container
```bash
docker run -p 8501:8501 \
  -e GOOGLE_API_KEY="your-key" \
  -e ANTHROPIC_API_KEY="your-key" \
  -e SUPABASE_URL="your-url" \
  -e SUPABASE_KEY="your-key" \
  fiscaudit-ai:latest
```

Access at: http://localhost:8501

---

### Option C: Traditional Server (Gunicorn + Nginx)

#### Step 1: Install Python 3.11+
```bash
python3 --version  # Should be 3.11+
```

#### Step 2: Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

#### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

#### Step 4: Setup Secrets
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml with your actual keys
```

#### Step 5: Run Locally (Testing)
```bash
streamlit run app.py
```

Access at: http://localhost:8501

#### Step 6: Deploy to Server
```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn --bind 0.0.0.0:8000 app:app
```

Setup Nginx reverse proxy to forward requests to Streamlit.

---

## 🔐 SECURITY BEST PRACTICES

### API Keys Management
✅ **DO:**
- Use `.streamlit/secrets.toml` (local development)
- Use Streamlit Cloud "Secrets" panel (production)
- Use environment variables in Docker
- Rotate keys regularly

❌ **DON'T:**
- Commit `secrets.toml` to GitHub
- Hardcode API keys in code
- Share API keys in messages/emails
- Use keys in version control

### Code Safety
✅ **DO:**
- Keep `.gitignore` updated (includes secrets.toml)
- Review logs for sensitive data
- Use HTTPS only
- Keep dependencies updated

❌ **DON'T:**
- Print API keys to console
- Log user data
- Expose error details to users
- Use outdated dependencies

---

## 📋 ENVIRONMENT VARIABLES

### For Local Development
Create `.streamlit/secrets.toml`:
```toml
google_api_key = "your-key"
anthropic_api_key = "your-key"
supabase_url = "your-url"
supabase_key = "your-key"
```

### For Docker
Pass as environment variables:
```bash
docker run -e GOOGLE_API_KEY="..." -e ANTHROPIC_API_KEY="..." ...
```

### For Streamlit Cloud
Add via Secrets panel in app settings (encrypted & secure)

### For Traditional Server
```bash
export GOOGLE_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
# Then run app
streamlit run app.py
```

---

## 🧪 TESTING AFTER DEPLOYMENT

### 1. Check Health
```bash
# Test that app loads
curl https://your-app-url.streamlit.app/
```

### 2. Test Functionality
1. Visit app URL
2. Upload test PDF
3. Enter AG-codes
4. Run audit
5. Check results

### 3. Monitor Logs
- **Streamlit Cloud:** View in "Manage app" → "Logs"
- **Docker:** `docker logs container-id`
- **Server:** Check server logs

### 4. Performance Check
- First load: < 5 seconds
- PDF upload: < 30 seconds
- Audit run: < 60 seconds

---

## 🐛 TROUBLESHOOTING

### Issue: "ModuleNotFoundError"
**Solution:**
```bash
pip install -r requirements.txt
# Verify: python -c "import streamlit; print(streamlit.__version__)"
```

### Issue: "API Key Error"
**Solution:**
1. Verify key is correct in secrets.toml
2. Check format (no extra spaces)
3. Test key manually on API provider
4. Ensure key has correct permissions

### Issue: "Port Already in Use"
**Solution:**
```bash
# Use different port
streamlit run app.py --server.port 8502
```

### Issue: "PDF Upload Fails"
**Solution:**
1. Check file size < 200 MB
2. Ensure it's valid PDF format
3. Check Gemini API quota
4. Review error message in logs

### Issue: "Slow Performance"
**Solution:**
1. Check internet connection
2. Monitor API rate limits
3. Reduce PDF size
4. Scale up server resources

---

## 📊 DEPLOYMENT CHECKLIST

### Before Pushing
- [ ] requirements.txt fixed (versions flexible)
- [ ] No `streamlit-aggrid==0.3.5.post2`
- [ ] `.streamlit/config.toml` created
- [ ] `.streamlit/secrets.toml.example` created
- [ ] `.gitignore` includes `.streamlit/secrets.toml`
- [ ] All code tested locally
- [ ] No hardcoded API keys in code

### Streamlit Cloud Deployment
- [ ] Repository pushed to GitHub
- [ ] Streamlit account created
- [ ] App connected in Streamlit Cloud
- [ ] Secrets added via panel (encrypted)
- [ ] App loads without errors
- [ ] All features tested

### Docker Deployment
- [ ] Dockerfile created
- [ ] Image builds successfully
- [ ] Container runs without errors
- [ ] All features tested
- [ ] Logs are clean

### Traditional Server
- [ ] Python 3.11+ installed
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] Secrets configured
- [ ] App runs with gunicorn
- [ ] Nginx reverse proxy configured

---

## ✅ WHAT'S NOW FIXED

### Requirements.txt
✅ Flexible version specifications (>= instead of ==)
✅ Removed problematic `streamlit-aggrid==0.3.5.post2`
✅ All dependencies are available on PyPI
✅ Streamlit Cloud compatible

### Streamlit Configuration
✅ `.streamlit/config.toml` - Professional dark theme
✅ `.streamlit/secrets.toml.example` - Template for secrets
✅ Proper structure for local & cloud deployment
✅ API key configuration documentation

### Documentation
✅ Complete deployment guide
✅ Multiple deployment options
✅ Security best practices
✅ Troubleshooting guide

---

## 🚀 NEXT STEPS

1. **Fix requirements.txt** ✅ (Already done)
2. **Add .streamlit files** ✅ (Already done)
3. **Push to GitHub:**
   ```bash
   git add requirements.txt .streamlit/
   git commit -m "Fix deployment - production-ready requirements"
   git push origin main
   ```

4. **Choose deployment:**
   - Streamlit Cloud (fastest): Follow "Option A"
   - Docker: Follow "Option B"
   - Server: Follow "Option C"

5. **Add secrets:**
   - Get your API keys
   - Add to appropriate location
   - Test functionality

6. **Monitor:**
   - Check logs for errors
   - Monitor performance
   - Gather user feedback

---

## 📞 SUPPORT

### Resources
- Streamlit Docs: https://docs.streamlit.io/
- Streamlit Cloud: https://share.streamlit.io/
- Deployment FAQ: https://docs.streamlit.io/streamlit-cloud/get-started

### Common Issues
- **API Keys:** Check console for error messages
- **Dependencies:** Run `pip list` to verify versions
- **Performance:** Monitor app dashboard for metrics
- **Secrets:** Ensure no typos in secret names

---

## ✨ YOU'RE READY TO DEPLOY!

All files are now production-ready:
- ✅ requirements.txt (fixed)
- ✅ .streamlit/config.toml (created)
- ✅ .streamlit/secrets.toml.example (created)
- ✅ Complete deployment guide

**Status: 🚀 READY FOR DEPLOYMENT**

Choose your deployment option above and follow the steps!

---

**Last Updated:** July 27, 2026
**Status:** ✅ Production Ready
**Version:** 1.0
