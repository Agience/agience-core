# Agience Color Scheme

Based on the logo's purple: **#9B7EBD** (HSL: 275° 30% 62%)

## Design System

### Typography
- **Primary Font**: DM Sans (variable weight 100-1000)
- **Monospace**: System monospace stack (for code only)

### Color Palette

#### Brand Purple (from logo)
- Primary: `hsl(275 30% 55%)` - #9B7EBD
- Used for: primary buttons, links, focus states, brand accents

#### Complementary Colors
- **Accent (Teal/Cyan)**: `hsl(195 60% 50%)` - Provides contrast and freshness
- **Destructive (Red)**: `hsl(0 84% 60%)` - For warnings and errors
- **Chart colors**: Purple-dominant with complementary accents

#### Neutrals
All neutrals have a subtle purple tint (275° hue) for brand cohesion:
- **Foreground**: `hsl(275 25% 15%)` - Dark purple-tinted text
- **Background**: White with purple-tinted grays
- **Borders**: `hsl(275 15% 90%)` - Soft purple-gray
- **Muted**: `hsl(275 15% 96%)` - Very light purple-gray backgrounds

### Dark Mode
Deeper purples with increased saturation:
- **Background**: `hsl(275 30% 8%)` - Deep purple-black
- **Primary**: `hsl(275 35% 65%)` - Lighter, more saturated purple
- **Accent**: `hsl(195 55% 55%)` - Brighter teal for contrast

### Shadows
All box shadows use the logo purple with varying opacity:
- Base: `rgba(155, 126, 189, 0.1)`
- Purple glow effects for special emphasis

## Implementation

Colors are defined as CSS variables in `src/index.css` and referenced through Tailwind's semantic tokens:
- `primary` - Brand purple
- `secondary` - Light purple backgrounds
- `accent` - Teal/cyan highlights
- `muted` - Subtle backgrounds with purple tint
- `border` - Purple-tinted borders

This approach keeps all color logic in CSS variables, making theme changes easier and avoiding hardcoded values in Tailwind config.
