"""Import Guitar Pro and MusicXML files as :class:`~guitarapp.tabs.Exercise`."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any

from .tabs import Exercise, Step
from .theory import STANDARD_TUNING, fret_for_midi

QUARTER_TICKS = 960
GUITAR_PRO_SUFFIXES = {".gp3", ".gp4", ".gp5"}
MUSICXML_SUFFIXES = {".musicxml", ".xml"}


def load_import(path: Path) -> list[Exercise]:
    suffix = path.suffix.lower()
    if suffix in GUITAR_PRO_SUFFIXES:
        return load_guitar_pro(path)
    if suffix in MUSICXML_SUFFIXES:
        return load_musicxml(path)
    raise ValueError(f"unsupported song format: {path.suffix or '(none)'}")


def load_guitar_pro(path: Path) -> list[Exercise]:
    try:
        import guitarpro
    except ImportError as error:  # pragma: no cover - dependency is installed in normal builds
        raise ImportError("Guitar Pro import requires the pyguitarpro package") from error

    song = guitarpro.parse(path)
    tracks = [track for track in song.tracks if not track.isPercussionTrack and track.strings]
    exercises = [_exercise_from_guitar_pro(song, track, len(tracks) > 1, index) for index, track in enumerate(tracks)]
    for exercise in exercises:
        exercise.source = str(path)
    return exercises


def _exercise_from_guitar_pro(song: Any, track: Any, multiple_tracks: bool = False, index: int = 0) -> Exercise:
    tuning_strings = sorted(track.strings, key=lambda string: string.number, reverse=True)
    tuning = tuple(string.value for string in tuning_strings)
    string_indexes = {string.number: index for index, string in enumerate(tuning_strings)}
    events: dict[float, dict[str, Any]] = {}

    for measure in track.measures:
        for voice in measure.voices:
            cursor = measure.start
            for beat in voice.beats:
                start = beat.start if beat.start is not None else cursor
                duration = beat.duration.time / QUARTER_TICKS
                cursor = start + beat.duration.time
                notes = []
                for note in beat.notes:
                    note_type = getattr(note.type, "name", note.type)
                    if note_type == "tie" or note.string not in string_indexes:
                        continue
                    notes.append((string_indexes[note.string], note.value))
                if not notes:
                    continue
                event = events.setdefault(float(start), {"notes": set(), "duration": 0.0})
                event["notes"].update(notes)
                event["duration"] = max(event["duration"], duration)

    if not events:
        raise ValueError(f"Guitar Pro track {track.name!r} contains no playable notes")
    first_beat = min(events)
    steps = [
        Step((beat - first_beat) / QUARTER_TICKS, tuple(sorted(event["notes"])), event["duration"])
        for beat, event in sorted(events.items())
    ]
    title = song.title or "Untitled Guitar Pro"
    if multiple_tracks:
        title = f"{title} — {track.name or f'Track {index + 1}'}"
    return Exercise(
        title=title,
        steps=steps,
        bpm=int(song.tempo),
        tuning=tuning,
        description=getattr(song, "artist", "") or "",
        source="",
        metadata={"format": "guitar-pro", "track": track.name or str(index + 1)},
    )


def load_musicxml(path: Path) -> list[Exercise]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ValueError(f"invalid MusicXML: {error}") from error
    part_names = {
        part.attrib.get("id", ""): (_findtext(part, "part-name") or "Part")
        for part in _findall(root, "score-part")
    }
    title = _findtext(root, "work-title") or _findtext(root, "movement-title") or path.stem
    tempo_node = next((node for node in _findall(root, "sound") if "tempo" in node.attrib), None)
    bpm = int(round(float(tempo_node.attrib["tempo"]))) if tempo_node is not None else 80
    exercises = []
    for part in _findall(root, "part"):
        exercise = _exercise_from_musicxml_part(part, part_names.get(part.attrib.get("id", ""), "Part"), title, bpm)
        if exercise is not None:
            exercise.source = str(path)
            exercises.append(exercise)
    if not exercises:
        raise ValueError("MusicXML contains no playable notes")
    return exercises


def _exercise_from_musicxml_part(part: ET.Element, part_name: str, title: str, bpm: int) -> Exercise | None:
    tuning = list(STANDARD_TUNING)
    divisions = 1.0
    measure_start = 0.0
    events: dict[float, dict[str, Any]] = {}

    for measure in _children(part, "measure"):
        cursor = 0.0
        max_cursor = 0.0
        last_onset: float | None = None
        measure_beats = 4.0
        for child in list(measure):
            tag = _local_name(child.tag)
            if tag == "attributes":
                divisions_text = _findtext(child, "divisions")
                if divisions_text:
                    divisions = float(divisions_text)
                time = _child(child, "time")
                if time is not None:
                    beats = float(_findtext(time, "beats", "4"))
                    beat_type = float(_findtext(time, "beat-type", "4"))
                    measure_beats = beats * 4.0 / beat_type
                for staff_tuning in _findall(child, "staff-tuning"):
                    line = int(staff_tuning.attrib["line"])
                    step = _findtext(staff_tuning, "tuning-step")
                    octave = _findtext(staff_tuning, "tuning-octave")
                    alter = int(_findtext(staff_tuning, "tuning-alter", "0"))
                    if step and octave and 1 <= line <= len(tuning):
                        tuning[len(tuning) - line] = _pitch_to_midi(step, int(octave), alter)
                continue
            if tag in {"backup", "forward"}:
                amount = float(_findtext(child, "duration", "0")) / divisions
                cursor += amount if tag == "forward" else -amount
                max_cursor = max(max_cursor, cursor)
                continue
            if tag != "note":
                continue

            duration = float(_findtext(child, "duration", "0")) / divisions
            is_chord = _child(child, "chord") is not None
            onset = last_onset if is_chord and last_onset is not None else measure_start + cursor
            if not is_chord:
                last_onset = onset
            max_cursor = max(max_cursor, cursor + duration)
            if _child(child, "rest") is None and not _has_tie_stop(child):
                pitch = _child(child, "pitch")
                if pitch is not None:
                    midi = _pitch_to_midi(
                        _findtext(pitch, "step", "C"),
                        int(_findtext(pitch, "octave", "4")),
                        int(float(_findtext(pitch, "alter", "0"))),
                    )
                    position = _musicxml_position(child, midi, tuple(tuning))
                    if position is not None:
                        event = events.setdefault(float(onset), {"notes": set(), "duration": 0.0})
                        event["notes"].add(position)
                        event["duration"] = max(event["duration"], duration)
            if not is_chord:
                cursor += duration

        measure_start += max(measure_beats, max_cursor)

    if not events:
        return None
    steps = [
        Step(beat, tuple(sorted(event["notes"])), event["duration"])
        for beat, event in sorted(events.items())
    ]
    return Exercise(
        title=f"{title} — {part_name}",
        steps=steps,
        bpm=bpm,
        tuning=tuple(tuning),
        metadata={"format": "musicxml", "part": part_name},
    )


def _musicxml_position(note: ET.Element, midi: int, tuning: tuple[int, ...]) -> tuple[int, int] | None:
    technical = _find(note, "technical")
    if technical is not None:
        string_text = _findtext(technical, "string")
        fret_text = _findtext(technical, "fret")
        if string_text and fret_text:
            string = int(string_text)
            fret = int(fret_text)
            if 1 <= string <= len(tuning) and fret >= 0:
                return len(tuning) - string, fret
    positions = fret_for_midi(midi, tuning, max_fret=24)
    if not positions:
        return None
    position = min(positions, key=lambda candidate: (candidate.fret, candidate.string))
    return position.string, position.fret


def _has_tie_stop(note: ET.Element) -> bool:
    return any(element.attrib.get("type") == "stop" for element in _findall(note, "tie") + _findall(note, "tied"))


def _pitch_to_midi(step: str, octave: int, alter: int = 0) -> int:
    pitch_classes = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    return (octave + 1) * 12 + pitch_classes[step.upper()] + alter


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _find(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element.iter() if child is not element and _local_name(child.tag) == name), None)


def _findall(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if child is not element and _local_name(child.tag) == name]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in list(element) if _local_name(child.tag) == name), None)


def _findtext(element: ET.Element, name: str, default: str | None = None) -> str | None:
    child = _find(element, name)
    return child.text if child is not None and child.text is not None else default
