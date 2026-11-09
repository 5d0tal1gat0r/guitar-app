# Home Navigation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visual Home dashboard and persistent sidebar navigation while preserving every existing Guitar Practice tool.

**Architecture:** Keep functional pages unchanged and place them in a `QStackedWidget` owned by `MainWindow`. Add a focused `home.py` module for the dashboard and its painted action cards, plus a `theme.py` module that owns the palette and application QSS. `MainWindow` remains the composition root and supplies Home with live library, history, and microphone state.

**Tech Stack:** Python 3.12, PySide6 widgets/QPainter, pytest, uv

**Spec:** `docs/superpowers/specs/2026-11-09-home-navigation-redesign-design.md`

## Global Constraints

- Preserve Practice, Library, Tuner, Metronome, Theory, Quiz, and Progress behavior.
- Keep the default window at 1000×720 and usable at 760×600.
- Use warm cream, deep navy, peach, honey, leafy green, and soft blue; no gradients, glass, emoji, or Unicode icon substitutes.
- Use real focusable Qt buttons for every route and Home action.
- Add no runtime dependency and change no stored data format.
- Do not package `.superpowers/`.

## Review Focus

- Microphone unavailable: Home shows “Microphone off” and every route remains usable; covered in Task 3.
- Empty library and history: Home shows honest zero/empty copy without indexing an empty list; covered in Task 2.
- Very long recent exercise title: the label wraps or elides without changing shell width; covered in Task 2.
- 760×600 window: the shell and six Home actions have no overlap or clipped controls; covered in Task 4.
- Keyboard-only use: sidebar and Home actions activate through Space/Enter and preserve visible focus; covered in Tasks 2 and 3.

---

### Task 1: Central theme and icon language

**Files:**
- Create: `src/guitarapp/theme.py`
- Create: `tests/test_theme.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `PALETTE: dict[str, str]`, `application_stylesheet() -> str`, and `tool_icon(name: str, size: int = 48) -> QIcon`.
- Consumes: PySide6 `QPainter`, `QPixmap`, and `QIcon`; no external assets.

- [ ] **Step 1: Write failing theme tests**

Add tests asserting the six approved palette roles have exact values, all text/surface combinations used by the QSS meet 4.5:1 contrast, the stylesheet contains visible `:focus`/`:focus-visible`-equivalent Qt states, and every supported tool name returns a non-null icon of the requested size.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run pytest tests/test_theme.py -q`

Expected: FAIL because `guitarapp.theme` does not exist.

- [ ] **Step 3: Implement the theme interfaces**

Use these palette values: cream `#FFF6E7`, navy `#1D2B3D`, peach `#EFA77D`, honey `#E3B652`, green `#B9D0A9`, blue `#91ACD2`. Paint consistent 2px geometric icons for `home`, `library`, `practice`, `tuner`, `metronome`, `theory`, `quiz`, and `progress`. The QSS owns typography hierarchy, sidebar buttons, action cards, toolbar controls, inputs, focus, disabled, and selected states.

- [ ] **Step 4: Ignore the local design workspace**

Add `.superpowers/` to `.gitignore`; do not remove the user's mockup files.

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run pytest tests/test_theme.py -q`

Expected: PASS.

Commit: `feat: add guitar practice visual system`

### Task 2: Home dashboard and real practice summary

**Files:**
- Create: `src/guitarapp/home.py`
- Create: `tests/test_home_ui.py`

**Interfaces:**
- Consumes: `History`, `load_library`, `PALETTE`, and `tool_icon`.
- Produces: `ActionCard(route: str, title: str, description: str, icon_name: str, parent: QWidget | None = None)`, `HomePage(history: History, library_loader: Callable = load_library)`, `HomePage.route_requested: Signal(str)`, `HomePage.refresh()`, and `HomePage.set_microphone_state(active: bool)`.

- [ ] **Step 1: Write failing Home tests**

Create an offscreen `QApplication` fixture and tests that assert:

- the six routes are `library`, `tuner`, `metronome`, `theory`, `quiz`, and `progress`;
- clicking and Space/Enter activation emit the matching route;
- a populated fake loader and `History` display library count, streak, and recent title;
- an empty loader/history displays `0 exercises`, `No practice yet`, and a `0 day` streak;
- a 120-character recent title does not increase `HomePage.minimumSizeHint().width()` beyond 560px;
- microphone state copy toggles between `Microphone ready` and `Microphone off`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_home_ui.py -q`

Expected: FAIL because `guitarapp.home` does not exist.

- [ ] **Step 3: Implement `ActionCard` and `HomePage`**

Build the asymmetric grid from the approved design: Library spans three rows; Tuner/Metronome, Theory/Quiz, and Progress plus a compact practice-summary region fill the remaining columns. Give every control an accessible name and keep labels mouse-transparent so the whole card activates reliably.

- [ ] **Step 4: Run focused tests and commit**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_home_ui.py -q`

Expected: PASS.

Commit: `feat: add visual practice home`

### Task 3: Persistent navigation shell

**Files:**
- Modify: `src/guitarapp/ui.py`
- Create: `tests/test_main_window_ui.py`

**Interfaces:**
- Consumes: `HomePage`, `application_stylesheet`, and existing page classes.
- Produces: `MainWindow(history: History | None = None, start_audio: bool = True)`, `MainWindow.show_route(route: str)`, `MainWindow.current_route: str`, `MainWindow.route_buttons: dict[str, QPushButton]`, and `MainWindow.pages: dict[str, QWidget]`.

- [ ] **Step 1: Write failing shell tests**

Instantiate `MainWindow(history=temp_history, start_audio=False)` and assert:

- Home is the initial route;
- all eight routes exist: `home`, `library`, `practice`, `tuner`, `metronome`, `theory`, `quiz`, `progress`;
- Home signals and sidebar clicks select the correct page and active button;
- `open_practice(exercise)` loads the exercise and selects Practice;
- `on_space()` still toggles only Practice and Metronome;
- `toggle_mic(False)` updates toolbar and Home state without starting audio;
- every route button has an accessible name and accepts keyboard focus.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -q`

Expected: FAIL because the stacked navigation interfaces do not exist.

- [ ] **Step 3: Replace top tabs with the shell**

Create a left navigation widget and `QStackedWidget`, retain the existing audio toolbar, connect `HomePage.route_requested` to `show_route`, and call `home_page.refresh()` whenever Home becomes current. Apply the application stylesheet once from `run()` and in `MainWindow` when an application already exists under tests.

- [ ] **Step 4: Preserve page-specific behavior**

Update `open_practice()` and `on_space()` to use route/page identity rather than `QTabWidget.currentWidget()`. Keep close cleanup unchanged.

- [ ] **Step 5: Run focused and full tests, then commit**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py tests/test_home_ui.py tests/test_theme.py -q`

Run: `uv run pytest -q`

Expected: all tests PASS.

Commit: `feat: add persistent guitar app navigation`

### Task 4: Responsive visual verification and release gate

**Files:**
- Modify as findings require: `src/guitarapp/home.py`, `src/guitarapp/theme.py`, `src/guitarapp/ui.py`
- Modify as findings require: `tests/test_home_ui.py`, `tests/test_main_window_ui.py`

**Interfaces:**
- Consumes: completed Home and navigation shell.
- Produces: verified behavior at 1000×720 and 760×600 with no new public interface.

- [ ] **Step 1: Add narrow-window regression assertions**

Show `MainWindow(start_audio=False)` offscreen at 760×600, process events, and assert the sidebar, stacked page, six Home cards, status labels, and toolbar controls have non-empty visible geometry contained by the window.

- [ ] **Step 2: Run the narrow-window test and fix only proven layout failures**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_main_window_ui.py -q`

Expected: PASS with no clipping assertion failures.

- [ ] **Step 3: Capture both review sizes**

Run a temporary offscreen capture script that saves 1000×720 and 760×600 PNGs under `/tmp`, with audio disabled and representative library/history data. Inspect both for hierarchy, painted icon visibility, palette consistency, overflow, and focus indication.

- [ ] **Step 4: Run final quality gates**

Run: `uv lock --check`

Run: `uv run pytest -q`

Run: `QT_QPA_PLATFORM=offscreen uv run python -c "from PySide6.QtWidgets import QApplication; from guitarapp.ui import MainWindow; app=QApplication([]); window=MainWindow(start_audio=False); window.show(); app.processEvents(); assert window.current_route == 'home'; window.close()"`

Run: `uv build`

Expected: lock check, full tests, GUI smoke, sdist, and wheel all PASS.

- [ ] **Step 5: Commit the verified responsive pass**

Commit only if Task 4 required changes: `fix: harden guitar app home layout`

