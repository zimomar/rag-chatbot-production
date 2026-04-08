# Specification: UI Refinement

## Context
The previous UI was a standard Streamlit layout. To make it "premium" and "modern", we've introduced custom CSS that overrides Streamlit defaults to create a Glassmorphism 2.0 effect.

## Design Principles
- **Color Palette**: Slate & Indigo (`#1e1b4b`, `#0f172a`, `#6366f1`).
- **Glassmorphism**: High blur (`24px`+) and low opacity borders.
- **Typography**: Inter for body, JetBrains Mono for technical data.
- **Visual Hierarchy**: Cards and status pills for complex data.

## Implementation Details
- **CSS Overrides**: Targeted `data-testid` elements in Streamlit.
- **Material Symbols**: Integrated Google Material Symbols for a modern icon set.
- **Helper Functions**: `render_sources` and `format_audit_report` to generate consistent HTML components.
