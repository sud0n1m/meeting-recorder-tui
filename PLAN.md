# Meeting Recording & Transcription System - Implementation Plan

## System Environment
- **OS**: Arch Linux (Omarchy)
- **Audio Server**: PipeWire 1.4.8 (with PulseAudio compatibility)
- **Working Directory**: /home/sudonim/sync/Meeting-Notes

## Overview
Build a **lightweight**, one-click meeting recorder for Linux that captures microphone + speaker audio, transcribes in real-time, summarizes with LLM, and exports to Obsidian vault.

**Design Philosophy**: Keep it simple, synchronous, and file-based. Direct piping with no intermediate services.

## Architecture

```
┌────────────────────────────────────────┐
│  TUI (Textual/Rich)                    │
│  ┌──────────────────────────────────┐  │
│  │  🎙️  Recording: 00:15:23         │  │
│  │  ▓▓▓▓▓░░░░ Mic  [########    ]   │  │
│  │  ▓▓▓▓▓▓░░░ Spk  [##########  ]   │  │
│  │                                  │  │
│  │  Press 'q' or Ctrl+C to stop     │  │
│  └──────────────────────────────────┘  │
└────────────┬───────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│  PipeWire Audio Capture              │
│  - Null sink (mix mic + speakers)    │
│  - Monitor levels → TUI              │
│  - Direct pipe to WhisperLive        │
└──────────┬───────────────────────────┘
           │ (audio stream)
           ▼
┌──────────────────────────────────────┐
│  WhisperLive + faster-whisper        │
│  - Real-time transcription           │
│  - Incremental file writes (chunks)  │
│  - transcript.txt updated live       │
└──────────┬───────────────────────────┘
           │ (on stop)
           ▼
┌──────────────────────────────────────┐
│  Summarizer (Ollama local LLM)       │
│  - Structured prompt:                │
│    • Summary                         │
│    • Decisions                       │
│    • Action items                    │
│    • Open questions                  │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│  Obsidian File Writer                │
│  - ~/Obsidian/Meetings/Transcripts/  │
│  - ~/Obsidian/Meetings/Summaries/    │
│  - Let Obsidian sync handle the rest │
└──────────────────────────────────────┘

Optional: Cloud LLM retry if unsatisfied with local summary
```

## Components

### 1. Audio Capture System
**Technology**: PipeWire 1.4.8 null sink + loopback

**Simple Approach**:
- Single null sink to mix mic + speaker monitor
- No per-channel separation (unless diarization needed later)
- Direct stream to transcription engine

**Implementation**:
- `pactl load-module` to create null sink + loopbacks
- Python subprocess to pipe audio to WhisperLive
- Cleanup on stop

**Tools**: `pactl`, `pavucontrol` (debugging only)

### 2. Real-time Transcription
**Primary**: WhisperLive + faster-whisper
- Great balance of latency/accuracy
- VAD built-in
- Supports CPU/GPU backends

**Optional Fallback**: whisper.cpp
- Only if very low-resource mode needed (laptop without GPU)
- Not implemented unless required

**Incremental Saving**:
- Write transcript chunks to file every few seconds
- Prevents data loss on crash
- Live-updating transcript file

### 3. Summarization Engine
**Primary**: Local LLM via Ollama
- Models: llama3.1:8b or mistral:7b
- Local HTTP endpoint (http://localhost:11434)

**Structured Prompt** (more predictable than generic "summarize"):
```
Based on this meeting transcript:

1. **Summary**: Brief overview (2-3 sentences)
2. **Decisions Made**: List key decisions
3. **Action Items**: Who does what, by when
4. **Open Questions**: Unresolved topics for follow-up
```

**Optional**: Cloud LLM retry
- Only if user is unsatisfied with local summary
- Manual trigger, not automatic
- OpenAI/Anthropic/Gemini as options

### 4. Control Interface (TUI)
**Interactive TUI using Textual**:
- `./meeting-recorder` - Launch TUI and start recording
- Live display shows:
  - Recording duration (HH:MM:SS timer)
  - Audio level indicators (mic + speakers)
  - Visual feedback that capture is working
  - Command hints (Press 'q' or Ctrl+C to stop)
- On stop: Show "Processing..." then exit

**TUI Layout**:
```
╭─── Meeting Recorder ────────────────────────╮
│                                             │
│  🎙️  Recording: 00:15:23                    │
│                                             │
│  Microphone:    ▓▓▓▓▓▓▓░░░░░░  [60%]       │
│  Speakers:      ▓▓▓▓▓▓▓▓▓░░░░  [75%]       │
│                                             │
│  Transcript: ~/Obsidian/Meetings/...        │
│                                             │
│  Press 'q' or Ctrl+C to stop recording      │
│                                             │
╰─────────────────────────────────────────────╯
```

**Why TUI**:
- Confidence it's working (live audio levels)
- Clear recording duration
- Simple one-command operation
- Professional look

**Implementation**:
- Textual for UI framework (reactive, async-friendly)
- Background threads for audio monitoring
- Update UI at ~10Hz for smooth levels
- Graceful cleanup on Ctrl+C

### 5. Obsidian Integration
**Dead Simple Approach**:
- Generate markdown files in configured directories
- Let Obsidian's built-in sync handle everything else
- No API calls, no plugins, just file writes

**Output Structure**:
```
~/Obsidian/Meetings/
├── Transcripts/
│   └── 2025-10-02_14-30_meeting.md
└── Summaries/
    └── 2025-10-02_14-30_summary.md
```

**Metadata Template** (minimal frontmatter):
```yaml
---
date: 2025-10-02
time: 14:30
duration: 45min
tags: [meeting, transcript]
---
```

**Optional Enhancement** (not required for MVP):
- Append link to daily note
- Only add if specifically requested

## Implementation Phases

### Phase 1: Audio Capture + TUI (Day 1-2)
**Tasks**:
1. Create PipeWire null sink + loopback setup script
2. Implement audio level monitoring (read from PipeWire)
3. Build basic TUI with Textual:
   - Recording timer
   - Audio level bars (mic + speakers)
   - Command hints
4. Test mic + speaker mixed capture with live feedback

**Deliverables**:
- `audio_setup.py` - PipeWire device management
- `tui.py` - Textual interface with live monitoring
- Working audio capture with visual feedback

### Phase 2: Transcription (Day 2-3)
**Tasks**:
1. Install WhisperLive + faster-whisper
2. Pipe audio directly to WhisperLive
3. Implement incremental transcript file writing (chunks every few seconds)
4. Test accuracy with sample audio

**Deliverables**:
- `transcribe.py` - WhisperLive integration
- Live-updating transcript.txt file

### Phase 3: Summarization (Day 3-4)
**Tasks**:
1. Verify Ollama is running (or install it)
2. Implement structured summarization prompt
3. Test summary quality with sample transcripts

**Deliverables**:
- `summarize.py` - Ollama LLM integration
- Structured summary template

### Phase 4: Obsidian Output (Day 4)
**Tasks**:
1. Create Obsidian directory structure
2. Implement markdown file writer with frontmatter
3. Test that Obsidian picks up files

**Deliverables**:
- `obsidian_writer.py` - File output module
- Auto-created Meetings directories

### Phase 5: Integration (Day 5)
**Tasks**:
1. Wire all components together in TUI
2. Add simple config file (YAML)
3. Update TUI with status messages:
   - "Recording..."
   - "Stopped - Transcribing..."
   - "Generating summary..."
   - "Saved to Obsidian ✓"
4. Test end-to-end workflow
5. Add error handling and graceful shutdown

**Deliverables**:
- `meeting-recorder` - Main TUI application
- `config.yaml` - User configuration
- Complete workflow with visual feedback

### Optional Enhancements (Later)
**Only if needed**:
- [ ] whisper.cpp fallback for low-resource mode
- [ ] Cloud LLM retry option
- [ ] Speaker diarization
- [ ] System tray indicator

## Technical Decisions

### Audio Format
- **Recording**: WAV (PCM 16-bit, 16kHz mono) - optimal for Whisper
- **Chunking**: 30-60 minute chunks for long sessions (prevents overheating, memory issues)
- **Streaming**: Direct pipe to WhisperLive (no intermediate files during recording)

### Model Selection
**Whisper Model** (use faster-whisper backend):
- Start with `medium` model (5GB RAM, good accuracy)
- Test on your hardware
- GPU if available, CPU fallback automatic

### LLM for Summarization
**Primary**: Local via Ollama
- llama3.1:8b (recommended, good balance)
- mistral:7b (alternative, faster)

**Optional**: Cloud as manual retry
- Only if unsatisfied with local summary
- User-triggered, not automatic

## Configuration Example

```yaml
# config.yaml (simplified)
audio:
  sample_rate: 16000
  chunk_minutes: 60  # split long recordings to prevent overheating

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
  keep_audio: true  # archive WAV files
  timestamp_format: "%Y-%m-%d_%H-%M"
```

## Dependencies

### System Packages (minimal)
```bash
pipewire              # Already installed
python3 python3-pip
ffmpeg                # For audio processing
```

### Python Packages (minimal)
```bash
whisper-live          # Real-time transcription
faster-whisper        # Backend
ollama                # Local LLM client
pyyaml                # Config file
textual               # TUI framework
```

### Services Required
- Ollama running locally (`ollama serve`)
- PipeWire (already running)

## Testing Strategy

### Manual Testing (keep it simple)
1. **TUI functionality**
   - Verify timer updates every second
   - Check audio level bars respond to sound
   - Test 'q' and Ctrl+C both stop gracefully
   - Confirm "Processing..." message appears

2. **5-minute test recording**
   - Verify both mic + speakers captured
   - Check audio quality (clarity, sync)
   - Watch levels confirm capture is working

3. **Transcription accuracy**
   - Read transcript for errors
   - Verify incremental saving works

4. **Summary quality**
   - Check structured output (summary, decisions, actions, questions)
   - Validate relevance

5. **Obsidian integration**
   - Confirm files appear in vault
   - Verify frontmatter is correct

6. **Long session test** (30-60 min)
   - Monitor resource usage
   - Check chunking works
   - Ensure no overheating
   - TUI remains responsive

## Success Criteria

✅ **Minimum Viable Product (MVP)**:
1. One command (`./meeting-recorder`) launches TUI and starts recording
2. TUI shows live recording duration and audio levels
3. Press 'q' or Ctrl+C to stop and process
4. Transcript saved to Obsidian within 2 minutes of stopping
5. Summary generated and saved with structured format
6. Works reliably on Arch Linux with PipeWire 1.4.8

✅ **Quality Targets**:
- Transcription accuracy: >90% for clear speech
- Processing time: <2x real-time (30min meeting = <60min processing)
- Summary captures key points and action items
- No manual intervention needed for happy path

## Risks & Mitigations (Local-only Context)

| Risk | Impact | Mitigation |
|------|--------|------------|
| GPU/driver breakage | High | Auto-fallback to CPU for Whisper |
| Vault path moves/changes | Medium | Validate config path on startup, fail gracefully |
| Overheating on long sessions | Medium | Chunk audio files every 30-60min |
| Transcription data loss on crash | Medium | Incremental file writes (chunks every few seconds) |
| Audio routing fails | Low | PipeWire stable; add cleanup on exit |
| Ollama not running | Medium | Check endpoint before summarizing, clear error message |

## Next Steps

1. ✅ Research and planning (DONE)
2. ✅ Simplified architecture (DONE)
3. Start Phase 1: Audio Capture
4. Iterate through phases 2-5
5. Test with real meetings

## Key Simplifications

**What Changed**:
- ❌ Removed intermediate services, message queues, complex IPC
- ❌ No scalability features (not needed for local-only)
- ❌ No automatic cloud fallbacks
- ✅ Direct piping: PipeWire → WhisperLive → Ollama → Files
- ✅ Simple Python subprocesses/threads
- ✅ Synchronous, file-based workflow
- ✅ Incremental transcript saving (crash-resistant)
- ✅ Structured summarization prompts
- ✅ Minimal dependencies
- ✅ TUI with live feedback (recording time, audio levels)

**Result**: ~50% less complexity, better UX, same functionality

## Resources

- WhisperLive: https://github.com/collabora/WhisperLive
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Ollama: https://ollama.ai
- PipeWire: https://wiki.archlinux.org/title/PipeWire
- Textual (TUI framework): https://textual.textualize.io
