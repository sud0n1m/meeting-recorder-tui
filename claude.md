# Meeting Recorder - Project Context

## Project Overview

A **lightweight, local-first meeting recording and transcription system** for Linux that captures microphone + speaker audio, transcribes in real-time using Whisper, summarizes with a local LLM (Ollama), and saves formatted notes to an Obsidian vault.

**Key Principle**: Keep it simple, synchronous, and file-based. No cloud dependencies, no complex services, no over-engineering.

## System Environment

- **OS**: Arch Linux (Omarchy)
- **Audio Server**: PipeWire 1.4.8 (with PulseAudio compatibility)
- **Python Version**: 3.x
- **Working Directory**: `/home/sudonim/sync/Meeting-Notes`

## Architecture Overview

```
User runs: ./meeting-recorder
    ↓
TUI launches (Textual) with live recording timer & audio levels
    ↓
PipeWire captures mic + speakers → mixed null sink
    ↓
Audio stream pipes directly to WhisperLive (faster-whisper backend)
    ↓
Transcript written incrementally to file (crash-resistant)
    ↓
On stop: Ollama generates structured summary
    ↓
Files saved to Obsidian vault directories
```

**Design Philosophy**:
- Direct piping (no intermediate services)
- Simple Python subprocesses/threads (no message queues)
- Synchronous, file-based workflow
- Incremental saves (data loss prevention)
- Local-first (optional cloud LLM retry only)

## Technology Stack

### Core Components
1. **Audio Capture**: PipeWire null sink + loopback (pactl commands)
2. **Transcription**: WhisperLive + faster-whisper (GPU/CPU auto-detect)
3. **Summarization**: Ollama (llama3.1:8b or mistral:7b)
4. **UI**: Textual (TUI framework)
5. **Output**: Markdown files → Obsidian vault

### Dependencies
```bash
# System packages
pipewire
python3 python3-pip
ffmpeg

# Python packages
whisper-live
faster-whisper
ollama
pyyaml
textual
```

### Services Required
- Ollama running locally (`ollama serve` on http://localhost:11434)
- PipeWire (already running on system)

## Project Structure

```
Meeting-Notes/
├── PLAN.md                    # Detailed implementation plan
├── claude.md                  # This file - project context
├── config.yaml               # User configuration
├── meeting-recorder          # Main entry point (TUI app)
├── src/
│   ├── audio_setup.py        # PipeWire device management
│   ├── transcribe.py         # WhisperLive integration
│   ├── summarize.py          # Ollama LLM integration
│   ├── obsidian_writer.py    # Markdown file generator
│   └── tui.py                # Textual interface
└── README.md                 # Usage documentation
```

## Key Features

### TUI Interface (Textual)
- **Recording timer**: Live HH:MM:SS display
- **Audio level bars**: Visual feedback for mic + speakers
- **Command hints**: "Press 'q' or Ctrl+C to stop"
- **Status messages**: Recording → Transcribing → Summarizing → Saved
- **Graceful shutdown**: Cleanup on exit

### Audio Capture
- Single null sink mixes mic + speaker monitor
- No per-channel separation (unless diarization added later)
- Direct stream to transcription engine
- Automatic cleanup on exit

### Real-time Transcription
- WhisperLive with faster-whisper backend
- Voice Activity Detection (VAD) built-in
- Incremental file writes (every few seconds)
- Live-updating transcript.txt file
- Model: `medium` (5GB RAM, good accuracy)

### Summarization
- **Structured prompt** for predictable output:
  1. Summary (2-3 sentences)
  2. Decisions Made (list)
  3. Action Items (who, what, when)
  4. Open Questions (follow-ups)
- Local LLM via Ollama (primary)
- Optional cloud retry (manual, user-triggered)

### Obsidian Integration
- Simple file writes to configured directories
- No API calls, no plugins
- Let Obsidian sync handle the rest
- Minimal frontmatter (date, time, duration, tags)

## Configuration

```yaml
# config.yaml (simplified)
audio:
  sample_rate: 16000
  chunk_minutes: 60  # split long recordings

whisper:
  model: medium
  backend: faster-whisper
  language: en
  device: auto  # GPU if available, else CPU

summarization:
  ollama_endpoint: http://localhost:11434
  model: llama3.1:8b

obsidian:
  vault_path: /home/sudonim/Obsidian
  transcript_dir: Meetings/Transcripts
  summary_dir: Meetings/Summaries

output:
  keep_audio: true
  timestamp_format: "%Y-%m-%d_%H-%M"
```

## Coding Conventions

### Python Style
- Type hints where helpful (not required everywhere)
- Docstrings for public functions
- Clear variable names (no abbreviations)
- Error handling with specific exceptions
- Logging for debugging (not print statements)

### Architecture Principles
1. **Keep it simple**: Avoid abstractions unless necessary
2. **Direct data flow**: No unnecessary indirection
3. **Fail gracefully**: Clear error messages, cleanup resources
4. **Incremental saves**: Write data frequently (crash-resistant)
5. **Monitor resources**: Chunk long sessions (prevent overheating)

### File Organization
- One responsibility per module
- Config loaded once at startup
- Shared state via simple data classes (no complex state management)
- Background tasks via threading (not async, unless Textual requires it)

## Implementation Phases

See [PLAN.md](./PLAN.md) for detailed phase breakdown. Summary:

1. **Phase 1** (Day 1-2): Audio Capture + TUI basics
2. **Phase 2** (Day 2-3): Transcription integration
3. **Phase 3** (Day 3-4): Summarization with Ollama
4. **Phase 4** (Day 4): Obsidian file output
5. **Phase 5** (Day 5): Integration + error handling

## Testing Strategy

### Manual Testing Focus
1. TUI responsiveness (timer, levels, stop commands)
2. 5-minute test recording (verify both audio sources)
3. Transcription accuracy (read output, check incremental saves)
4. Summary quality (structured format, relevance)
5. Obsidian integration (files appear, frontmatter correct)
6. Long session (30-60 min, monitor resources)

### Key Validation Points
- Audio levels visible in TUI → confirms capture working
- Transcript updates during recording → confirms streaming
- Clean shutdown on Ctrl+C → confirms resource cleanup
- Files in Obsidian vault → confirms end-to-end flow

## Known Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| GPU/driver breakage | Auto-fallback to CPU for Whisper |
| Vault path changes | Validate config on startup |
| Overheating (long sessions) | Chunk audio every 30-60min |
| Crash during recording | Incremental transcript writes |
| Ollama not running | Check endpoint before summarizing |

## Success Criteria (MVP)

1. ✅ One command launches TUI and starts recording
2. ✅ Live recording duration and audio levels visible
3. ✅ 'q' or Ctrl+C stops and processes
4. ✅ Transcript saved to Obsidian within 2 minutes
5. ✅ Structured summary generated and saved
6. ✅ Works reliably on Arch + PipeWire 1.4.8

## Usage (Future)

```bash
# Start recording (launches TUI)
./meeting-recorder

# During recording:
# - Watch timer and audio levels
# - Press 'q' or Ctrl+C to stop

# After stopping:
# - Automatic transcription
# - Automatic summarization
# - Files saved to Obsidian vault
```

## Resources

- **PLAN.md**: Detailed implementation plan with phases
- WhisperLive: https://github.com/collabora/WhisperLive
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Ollama: https://ollama.ai
- Textual: https://textual.textualize.io
- PipeWire: https://wiki.archlinux.org/title/PipeWire

## Notes for AI Assistants

When working on this project:

1. **Simplicity first**: Don't add complexity. If tempted to add a feature, ask if it's needed for MVP.
2. **Direct implementation**: Avoid frameworks, abstractions, or "scalable" patterns.
3. **File-based**: Everything should be readable/writable as files.
4. **Local-first**: No cloud services in the critical path.
5. **User feedback**: TUI should always show what's happening.
6. **Error handling**: Fail gracefully with clear messages.
7. **Resource cleanup**: Always cleanup PipeWire devices on exit.
8. **Incremental saves**: Write data frequently, don't wait until the end.

**Remember**: This is a personal productivity tool, not production software. Optimize for reliability and simplicity, not scalability.
