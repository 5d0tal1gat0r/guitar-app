# Guitar Practice

Open-source guitar practice app for Linux. It listens through your microphone,
tells you whether each note you play is right, wrong, out of tune or missed,
and helps you build speed with a sample-accurate metronome.

## Features

- **Practice**: play an exercise along with a one-bar count-in and click. Each
  note is judged live (correct / out of tune / wrong / missed) and shown on a
  fretboard, with timing and accuracy at the end. At 90 % or better it suggests
  +5 BPM; under 60 % it tells you to slow down.
- **Library**: bundled exercises, your own `.tab` files, pasted ASCII tabs,
  Guitar Pro `.gp3`/`.gp4`/`.gp5`, and MusicXML `.musicxml`/`.xml` files.
- **Generator**: new exercises on the spot: scale runs (with 3- or 4-note
  groupings), random melodies in any key and scale, arpeggios, chromatic finger
  drills, and "find every C" fretboard drills.
- **Tuner**: note, frequency, cents, and which string to turn which way.
- **Metronome**: 20–300 BPM, tap tempo, time signatures, subdivisions, and a
  speed trainer that raises the tempo every N bars up to a target.
- **Theory**: scales and chords in every key, interval names, step patterns,
  diatonic chords with Roman numerals, and the whole pattern on the fretboard.

Detection is monophonic: play one note at a time. For a chord step, any one of
its notes counts.

## Install and run

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and PortAudio
(`sudo pacman -S portaudio` on Arch).

```bash
uv sync
uv run guitar-app
```

## Tab format

Plain ASCII tab with optional `#` headers. See `src/guitarapp/tabs.py` for the
full description.

```
# title: A minor pentatonic, box 1
# bpm: 70
# tuning: E2 A2 D3 G3 B3 E4
# beats-per-note: 1
e|-----------------------5-8-|
B|-------------------5-8-----|
G|---------------5-7---------|
D|-----------5-7-------------|
A|-------5-7-----------------|
E|---5-8---------------------|
```

Rhythm is not read from dash spacing; each fret number column is one step of
`beats-per-note` beats. Imported uneven rhythms are stored with optional
`# durations:` and `# beats:` headers. Your files live in
`~/.local/share/guitar-app/songs/`.

The app does not ship copyrighted songs. Import or paste tabs you have the
right to use.

## Development

```bash
uv sync --extra dev
uv run pytest
```

| Module | Purpose |
| --- | --- |
| `theory.py` | notes, frequencies, scales, chords, fretboard maps |
| `pitch.py` | YIN pitch detection, note stabilisation and onset reset |
| `practice.py` | step windows and verdicts (pure, time passed in) |
| `metronome.py` | sample-accurate click rendering, tap tempo |
| `tabs.py` | tab parser, renderer, library loader |
| `importers.py` | Guitar Pro and MusicXML import |
| `generator.py` | exercise generators |
| `audio.py` | microphone capture |
| `widgets.py`, `ui.py` | Qt (PySide6) interface |

## License

MIT
