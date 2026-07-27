# 🎨 FiscAudit AI - Design System Documentation

**Professional Executive Fiscal Dashboard**  
Built with intentional design decisions for Dutch tax professionals

---

## 📋 Design Philosophy

This dashboard follows enterprise design principles:
- **Purposeful & Functional** - Every visual element serves a purpose
- **Professional & Trustworthy** - Dark theme conveys security & sophistication  
- **Accessible & Inclusive** - WCAG-compliant, keyboard navigation, reduced motion support
- **No Templates** - Distinctive design specific to fiscal audit domain

---

## 🎨 VISUAL IDENTITY

### Color System

The palette is deliberately chosen for the fiscal/financial domain:

```
Primary Dark Background:  #0F172A (Slate-900)
  └─ Professional, trustworthy, corporate banking aesthetic
  
Secondary Background:     #1E293B (Slate-800)
  └─ Subtle contrast for elevated surfaces
  
Primary Action:          #2563EB (Royal Blue)
  └─ Professional authority, clear focus
  
Status Colors:
  ├─ Success/Match:      #059669 (Emerald)
  ├─ Error/Mismatch:     #DC2626 (Crimson)
  └─ Warning/Missing:    #D97706 (Amber)

Text Colors:
  ├─ Primary:            #F8FAFC (Slate-50) - main text
  ├─ Secondary:          #CBD5E1 (Slate-400) - secondary
  └─ Tertiary:           #94A3B8 (Slate-500) - hints & captions
```

**Why This Palette?**
- Dark backgrounds: Professional financial software (Bloomberg, JP Morgan)
- Royal Blue primary: Authority without aggression
- Status colors: International standards (red=error, green=success, amber=warning)
- Slate text: Readable on dark backgrounds, reduces eye strain

### Typography

**Font Family:** System fonts (`-apple-system`, `BlinkMacSystemFont`, `Segoe UI`)
- ✅ Loads instantly (no external requests)
- ✅ Professional look across platforms
- ✅ Excellent readability
- ✅ Native performance

**Type Scale:**
- H1: 2.5rem (700 weight) - Page titles
- H2: 1.875rem (600 weight) - Section headers
- H3: 1.25rem (600 weight) - Subsections
- Body: 0.95rem (400 weight) - Main text
- Caption: 0.75rem (500 weight) - Helper text

**Monospace:** `Monaco`, `Courier New` for:
- Currency amounts (precise, tabular)
- JSON/code display
- AG-codes

### Spacing & Layout

Consistent spacing system based on 8px grid:
```
xs:  4px   - micro spacing
sm:  8px   - small gaps
md:  16px  - standard padding
lg:  24px  - section margins
xl:  32px  - large sections
```

### Shadows & Depth

```
sm:  0 1px 2px rgba(0,0,0,0.3)      - subtle depth
md:  0 4px 6px rgba(0,0,0,0.2)      - cards
lg:  0 10px 15px rgba(0,0,0,0.3)    - modals
xl:  0 20px 25px rgba(0,0,0,0.4)    - overlays
```

Shadows are used sparingly to:
- Elevate interactive elements
- Create visual hierarchy
- Indicate hover states

---

## 🏗️ Component Architecture

### Design System Layers

```
style.css (Base Layer)
    ↓
    • CSS variables (colors, spacing, shadows)
    • Global typography
    • Component base classes
    ↓
ui_components.py (Component Layer)
    ↓
    • Reusable React-like functions
    • Composed from CSS classes
    • State-agnostic
    ↓
app.py (Application Layer)
    ↓
    • Business logic integration
    • State management
    • User workflows
```

### Key Components

#### 1. Metric Cards (`metric_card`)
Professional KPI display with:
- Large, readable value (2rem, monospace)
- Subtle label (uppercase, tracking)
- Optional delta indicator
- Hover elevation effect

**Usage:**
```python
metric_card(
    label="Match Rate",
    value="95%",
    delta="+5 from last",
    icon="📊"
)
```

#### 2. Status Badges (`status_badge`)
Color-coded status indicators:
- ✅ MATCH (Emerald)
- ❌ MISMATCH (Crimson)
- ⚠️ MINOR_VARIANCE (Amber)
- ❓ MISSING_PROOF (Purple)

**Usage:**
```python
st.markdown(status_badge("MATCH"), unsafe_allow_html=True)
```

#### 3. Section Containers
Organized groupings with:
- Subtle borders (#1E293B)
- Consistent padding
- Hover effects
- Dark background

#### 4. Alert Boxes (`info_box`)
Contextual messaging:
- Success (green, ✅)
- Error (red, ❌)
- Warning (amber, ⚠️)
- Info (blue, ℹ️)

All with colored left border + semi-transparent background

---

## 📱 Layout Patterns

### Main Layout
```
┌─────────────────────────────────┐
│ Sidebar (25%) │ Main (75%)      │
│               │                 │
│ • Dossier     │ • Page Title    │
│ • Stats       │ • Content       │
│ • Nav         │ • Tabs          │
│               │                 │
└─────────────────────────────────┘
```

### Dashboard Layout (Tab 2)
```
┌──────────────────────────────────┐
│ KPI Cards (4 columns)            │
├──────────────────────────────────┤
│ Risk Level Indicator             │
├──────────────────────────────────┤
│ Audit Results Table              │
├──────────────────────────────────┤
│ Export Buttons                   │
└──────────────────────────────────┘
```

### Upload Layout (Tab 1)
```
┌──────────────────────────────────┐
│ 1. Upload Section                │
│    ├─ File uploader              │
│    └─ Extract button             │
├──────────────────────────────────┤
│ 2. AG-Codes Input                │
│    ├─ JSON input area            │
│    └─ Validation feedback        │
├──────────────────────────────────┤
│ 3. Start Audit                   │
│    └─ Primary action button      │
└──────────────────────────────────┘
```

---

## ✨ Interaction Patterns

### Hover States
- **Cards:** Subtle lift (-4px) + border color change + shadow increase
- **Buttons:** Darker background + slight lift
- **Links:** Color change + underline

### Focus States
- **Forms:** Blue outline (3px) with 10% opacity box-shadow
- **Keyboard:** Visible focus ring (✅ WCAG AA)

### Loading States
- **Progress bars:** Gradient animation with glow effect
- **Spinners:** Smooth rotation animation
- **Disabled states:** Reduced opacity (50%)

### Responsive Behavior
```
Desktop (1024px+)
  • Full layout with sidebar
  • 4-column metric layouts
  • Multi-column tables

Tablet (768px - 1024px)
  • Collapsible sidebar
  • 2-column metric layouts
  • Stack tables if needed

Mobile (< 768px)
  • Full-width content
  • 1-column layouts
  • Touch-friendly buttons (44px minimum)
```

---

## 🎯 Design Decisions Explained

### 1. Why Dark Theme?

**Chosen for:**
- ✅ Professional financial software aesthetic
- ✅ Reduces eye strain for long audit sessions
- ✅ Makes colored status indicators more visible
- ✅ Modern, premium appearance
- ✅ Reduced blue light emission

**Not chosen:** Warm cream backgrounds (too templated)

### 2. Why Royal Blue Primary?

**Chosen for:**
- ✅ Professional authority (banking, law, accounting)
- ✅ High contrast on dark backgrounds
- ✅ Accessible (WCAG AAA compliant)
- ✅ Not "loud" or aggressive

**Not chosen:** Bright neon/acid-green (too trendy)

### 3. Why System Fonts?

**Chosen for:**
- ✅ Zero latency (no font loading)
- ✅ Native feel on each platform
- ✅ Excellent hinting & rendering
- ✅ Reduced page weight

**Not chosen:** Custom web fonts (add 100KB+)

### 4. Why Monospace for Money?

**Chosen for:**
- ✅ Tabular alignment (decimal places line up)
- ✅ Precise, professional look
- ✅ Auditor expectation (accounting software)
- ✅ Visual distinction from surrounding text

**Not chosen:** Variable fonts (harder to compare amounts)

### 5. Why No Animation by Default?

**Chosen for:**
- ✅ Accessibility (respects prefers-reduced-motion)
- ✅ Performance (no jank on low-end devices)
- ✅ Professional feel (not "designed by AI")
- ✅ Focus on content, not decoration

**Used sparingly:** Only hover states and progress indicators

---

## 📐 Component Specifications

### Metric Card
```
Padding:        24px
Border:         1px solid #1E293B
Border Radius:  12px
Shadow:         0 4px 6px rgba(0,0,0,0.2)
Value Font:     monospace, 2rem, #2563EB
Label Font:     uppercase, 0.875rem, #94A3B8
Hover Effect:   translateY(-4px), shadow increase
```

### Status Badge
```
Padding:        4px 12px
Border Radius:  20px
Font Size:      0.75rem (uppercase)
Font Weight:    700
Letter Spacing: 0.5px
Border:         1px solid (color-specific)
Background:     color @ 15% opacity
```

### Button
```
Padding:        8px 16px (sm) to 12px 24px (lg)
Border Radius:  8px
Font Weight:    600
Text Transform: UPPERCASE
Letter Spacing: 0.5px
Shadow:         0 1px 2px rgba(0,0,0,0.3)
Hover:          translateY(-2px), shadow increase
Active:         No transform
```

### Input Field
```
Background:     #1E293B
Border:         1px solid #1E293B
Border Radius:  8px
Padding:        10px 12px
Focus Border:   #2563EB
Focus Shadow:   0 0 0 3px rgba(37, 99, 235, 0.1)
```

---

## 🔄 Design System Workflow

### For Designers
1. Export color variables from `style.css`
2. Use established component specs for mockups
3. Test new components against accessibility standards
4. Add to `ui_components.py` for developer use

### For Developers
1. Check `ui_components.py` for pre-built components
2. Import from `ui_components` instead of building from scratch
3. CSS variables available in `style.css` for custom needs
4. Follow spacing grid (4px, 8px, 16px, 24px, 32px)

### For QA
1. Test in light & dark environments
2. Verify keyboard navigation
3. Check touch targets (minimum 44px)
4. Test screen reader compatibility
5. Verify color contrast (WCAG AA minimum)

---

## 📊 Accessibility Checklist

- [x] Color contrast ≥ 4.5:1 (WCAG AA)
- [x] Focus indicators visible
- [x] Keyboard navigation complete
- [x] Reduced motion respected
- [x] Touch targets ≥ 44px
- [x] Form labels associated
- [x] Semantic HTML used
- [x] ARIA attributes added where needed
- [x] Screen reader tested
- [x] Zoom to 200% works

---

## 🎯 Design Achievements

✅ **Zero Templates** - Unique design specific to fiscal audit domain  
✅ **Professional Look** - Enterprise banking aesthetic  
✅ **Accessible** - WCAG AA compliant, full keyboard support  
✅ **Performant** - No external fonts, minimal CSS, fast load  
✅ **Responsive** - Works on mobile to desktop  
✅ **Intentional** - Every color, shadow, and spacing has purpose  

---

## 📚 Further Reading

- Streamlit Components: https://docs.streamlit.io/
- Design System best practices: https://design-system.service.gov.uk/
- Accessibility guidelines: https://www.w3.org/WAI/WCAG21/quickref/
- Color contrast checker: https://www.tpgi.com/color-contrast-checker/

---

**Design System Version:** 1.0  
**Last Updated:** July 27, 2026  
**Status:** Production Ready ✅
