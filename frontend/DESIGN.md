# EvalPilot Console Design

## Direction

EvalPilot is a professional evaluation console, not a sci-fi dashboard. The
interface uses a calm light surface, strong typographic hierarchy and restrained
state colour so reviewers can answer four questions immediately:

1. Is the candidate safe to release?
2. How many scenarios regressed?
3. Which evidence supports the verdict?
4. What should be done next?

## Principles

- Content first: no decorative grids, scanlines, glows, chamfers or ambient animation.
- One primary accent: blue marks navigation, links and primary actions.
- State colour is semantic: red for regression/block, amber for review, green for pass/live.
- White cards on a soft gray field; 1px borders and subtle shadows only.
- Normal Chinese typography: no uppercase transform or wide letter spacing for UI labels.
- Identifiers, evidence ids, model ids and scenario ids remain monospace and unchanged.
- Dense where comparison matters; generous where reading matters.

## Surfaces

- Page: `#f4f6f8`
- Card: `#ffffff`
- Muted surface: `#f8fafc`
- Border: `#d9e1ea`
- Primary text: `#172033`
- Secondary text: `#5b6779`
- Primary action: `#2563eb`
- Regression/block: `#dc2626`
- Review/warning: `#d97706`
- Pass/live: `#16a34a`

## Layout

- Header: run identity, versions, provenance and runtime status.
- Navigation: plain horizontal tabs with a blue active underline.
- Console: comparison chart and case record on the left, metrics/verdict on the right.
- Investigation: procedure timeline, root-cause/decision panel, counterfactual replay, evidence drawer.
- Market: editorial report blocks with measured/target/assumption labels.

## Accessibility

- Status is always stated in text, never carried by colour alone.
- Focus rings remain visible.
- Motion is absent by default.
- Tables scroll horizontally on narrow screens instead of collapsing columns.
