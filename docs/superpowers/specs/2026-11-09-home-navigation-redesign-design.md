# Home Navigation Redesign

## Intent

Turn Guitar Practice from a row of utility tabs into an inviting practice
dashboard. A beginner should immediately understand what they can do, see a
clear next action, and reach every existing tool without losing functionality.

## Approved direction

- The application opens on a new Home screen.
- A persistent left navigation rail replaces the top-level tab bar.
- “Practice a song” is the dominant action and opens the Library.
- Home also offers visual shortcuts to Tuner, Metronome, Theory, Quiz, and
  Progress.
- Existing Practice, Library, Tuner, Metronome, Theory, Quiz, and Progress
  behavior remains intact.
- The Home screen shows real microphone status, available exercise count,
  practice streak, and most recently practiced exercise when available.
- Selecting an exercise from Library or Theory still opens Practice directly.

## Visual system

The interface uses warm cream as its main surface, deep navy for structure and
text, and restrained peach, honey, leafy green, and soft blue as functional
accents. It should feel optimistic and musical without neon colors, gradients,
glass effects, generic card grids, emoji, or decorative clutter.

The Home composition is intentionally asymmetric: one large practice action
and a compact set of tool actions. Typography, spacing, borders, and color do
the visual work. Tool illustrations use crisp Qt-painted geometry with a
consistent stroke language rather than Unicode symbols.

## Interaction and layout

- Every navigation item and Home action is a real keyboard-focusable Qt button.
- The active destination is visually obvious in the navigation rail.
- Home data refreshes whenever the user returns Home.
- The microphone state updates immediately when listening is enabled or fails.
- Space continues to start/stop Practice and Metronome on their respective
  screens.
- The intended desktop size remains 1000×720; the interface must remain usable
  at 760×600 without overlapping or clipped controls.
- Long exercise names wrap or elide inside their allocated region instead of
  resizing the shell.

## Boundaries

- No new runtime dependency.
- No change to audio, pitch detection, exercise parsing, metronome timing, or
  stored history formats.
- No removal or renaming of existing user-facing tools.
- The local `.superpowers/` mockup workspace is not shipped or packaged.

## Acceptance

- All existing tests remain green.
- New UI tests prove Home routing, sidebar routing, active state, Home metrics,
  empty states, keyboard activation, and microphone-state updates.
- Offscreen startup and scripted navigation pass with audio disabled.
- A rendered 1000×720 and 760×600 review shows the approved hierarchy, intact
  icons, coherent palette, and no clipping.

