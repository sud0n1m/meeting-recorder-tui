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

## Version 0.2 - Planned Features

### Feature 0: Improved TUI UX with Pre-Recording Screen (Priority)

**Current Problems**:
1. Recording starts immediately on launch (no control)
2. Only 'q' keybinding available (limited interaction)
3. No cancel option (always processes transcription)
4. No clear action buttons or visual feedback for controls
5. No way to review settings before starting

**Proposed Solution**: Multi-screen TUI with proper workflow.

#### Screen 1: Pre-Recording Dashboard (New)

```
╭─── Meeting Recorder ─────────────────────────────────────╮
│                                                           │
│  🎙️  Ready to Record                                     │
│                                                           │
│  Configuration:                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ • Whisper Model: base (CPU)                         │ │
│  │ • Output: ~/Documents/Obsidian Vault/meetings       │ │
│  │ • LLM: qwen3:8b-q8_0 @ ollama.firecorn.net          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  Recent Recordings: (3 most recent)                       │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ • 2025-10-18 14:30 - Team Standup (45 min)         │ │
│  │ • 2025-10-17 10:00 - Product Review (1h 20min)     │ │
│  │ • 2025-10-16 11:30 - Client Call (30 min)          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │         Press [R] or [Enter] to Start Recording     │ │
│  │         Press [Q] to Quit                           │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
╰───────────────────────────────────────────────────────────╯

Footer: [R]ecord  [Q]uit  [?]Help
```

**Pre-Recording Screen Features**:
- Show current configuration summary
- Display 3 most recent recordings with durations
- Clear call-to-action to start recording
- System checks (audio devices, disk space, Ollama connection)
- **No title input yet** - start recording first, then name it

#### Screen 2: Recording in Progress (Current Screen - Improved)

```
╭─── Meeting Recorder ─────────────────────────────────────╮
│                                                           │
│  🔴 RECORDING: 00:15:23                                   │
│                                                           │
│  Meeting Title:                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ > Team Standup_                                      │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  Started: 2025-10-19 14:30                                │
│                                                           │
│  Audio Levels:                                            │
│  Microphone:    ▓▓▓▓▓▓░░░░░  [60%]                       │
│  Speakers:      ▓▓▓▓▓▓▓▓░░░  [75%]                       │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  [S] Stop & Save  |  [C] Cancel  |  [P] Pause       │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
╰───────────────────────────────────────────────────────────╯

Footer: [S]top&Save  [C]ancel  [P]ause  [T]itle  [?]Help
```

**Recording Screen Improvements**:
- Clear "RECORDING" indicator (🔴 red circle)
- **Editable meeting title field** (only appears after recording starts)
- Display recording start timestamp
- Prominent action buttons
- Status message area
- Visual separation of controls
- Press `T` or click field to edit title while recording

**Meeting Title Behavior**:
- **Title input only appears once recording has started**
- Default value: "Untitled" (displayed but not editable by default)
- **Editing workflow**:
  1. Press `T` hotkey to activate title editing mode
  2. Title field becomes editable with cursor
  3. Type new title (replaces "Untitled" or edits existing)
  4. Press `Enter` to save/store the new title
  5. Press `Esc` to cancel editing and keep previous title
  6. Field returns to display-only mode
- Can edit title multiple times during recording
- Final filename format: `YYYY-MM-DD_HH-MM-SS_Title.md`
  - Example: `2025-10-19_14-30-00_Team-Standup.md`
  - Example: `2025-10-19_14-30-00_Untitled.md` (if not changed)
- Title is sanitized (spaces → hyphens, remove special chars)
- Timestamp is always prepended automatically (captured at recording start)
- Title appears in markdown frontmatter and heading
- Can update title mid-recording if meeting topic changes or becomes clear

#### Screen 3: Processing (New - Non-interactive)

```
╭─── Meeting Recorder ─────────────────────────────────────╮
│                                                           │
│  ⏹️  Recording Stopped                                    │
│                                                           │
│  Processing:                                              │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ ✓ Audio saved (45:23, 84 MB)                        │ │
│  │ ⌛ Transcribing... (est. 2 min remaining)            │ │
│  │ ⏳ Summarization (pending)                           │ │
│  │ ⏳ Save to vault (pending)                           │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  Please wait... This will close automatically.            │
│                                                           │
╰───────────────────────────────────────────────────────────╯

Footer: Processing... (cannot cancel)
```

**Processing Screen Features**:
- Step-by-step progress indication
- Estimated time remaining
- Cannot cancel (committed to processing)
- Auto-closes when complete

---

### Comprehensive Keybinding Plan

#### Global Keybindings (all screens):
| Key | Action | Description |
|-----|--------|-------------|
| `?` | Show help | Display keybinding reference overlay |
| `Ctrl+C` | Emergency exit | Force quit (cleanup only, no processing) |
| `F1` | Help | Same as `?` |
| `Esc` | Context-dependent | Back/Cancel based on current screen |

#### Pre-Recording Screen:
| Key | Action | Description |
|-----|--------|-------------|
| `R` / `Enter` / `Space` | Start recording | Initialize audio and begin recording |
| `Q` | Quit | Exit application cleanly |
| `O` | Open settings | Edit config file (future) |
| `L` | View logs | Show recent recording logs (future) |
| `↑` / `↓` | Navigate recent | Browse recent recordings (future) |

#### Recording Screen:
| Key | Action | Description |
|-----|--------|-------------|
| `S` / `Enter` | Stop & Save | Stop recording, process, and save (when not editing title) |
| `C` / `Esc` | Cancel | Stop recording, cleanup, no processing (when not editing) |
| `T` | Edit Title | Activate title editing mode |
| `Enter` | Save Title | Save title and exit editing mode (when editing) |
| `Esc` | Cancel Edit | Cancel title edit and keep previous value (when editing) |
| `P` / `Space` | Pause/Resume | Pause recording (future v0.3) |
| `M` | Mute mic | Temporarily mute microphone (future) |
| `Q` | Stop & Save | Same as `S` (legacy compatibility) |

**Note**: Keybindings are context-aware. When editing title, `Enter` saves title and `Esc` cancels edit. Otherwise, `Enter` stops recording and `Esc` cancels recording.

#### Processing Screen:
| Key | Action | Description |
|-----|--------|-------------|
| None | (non-interactive) | Wait for completion |
| `Ctrl+C` | Force quit | Stop processing and exit (cleanup only) |

---

### Implementation Plan (v0.2)

**Phase 1: State Management**
1. Add app state enum: `READY`, `RECORDING`, `PROCESSING`, `DONE`
2. Implement state transitions and guards
3. Add state-dependent rendering logic

**Phase 2: Pre-Recording Screen**
1. Create `DashboardScreen` widget
2. Add recent recordings display (read from output directory)
3. Add configuration summary widget
4. Implement system health checks
5. Defer recording start until user action

**Phase 3: Enhanced Recording Screen**
1. Update instruction text with multiple keybindings
2. Add visual button-style UI elements
3. Improve status message prominence
4. Add recording indicator (🔴 pulsing if possible)

**Phase 4: Processing Screen**
1. Create `ProcessingScreen` widget
2. Add step-by-step progress indicators
3. Implement progress state tracking
4. Add estimated time remaining (basic)

**Phase 5: Keybinding Implementation**
1. Update `BINDINGS` list with new keys
2. Add `action_*` methods for each keybinding
3. Implement state-aware keybinding handling
4. Add cancel functionality (no processing)

**Phase 6: Footer/Status Bar**
1. Add dynamic footer showing available keybindings
2. Update footer based on current screen/state
3. Optional: Add help overlay (`?` key)

---

### User Workflow (v0.2)

**Happy Path**:
1. Launch `./meeting-recorder`
2. See pre-recording dashboard with recent recordings and config
3. Press `R` or `Enter` to start recording
4. Recording screen shows timer and audio levels
5. Press `S` or `Enter` when done
6. Processing screen shows progress
7. Auto-exits when complete, files saved

**Cancel Path**:
1. Launch `./meeting-recorder`
2. Press `R` to start recording
3. Realize recording not needed
4. Press `C` or `Esc` to cancel
5. Cleanup happens, no files saved
6. Returns to pre-recording dashboard (or exits)

**Panic Path**:
1. Any screen: Press `Ctrl+C`
2. Immediate cleanup and exit
3. No processing, emergency shutdown

---

### Design Principles

1. **Progressive Disclosure**: Show options when relevant
2. **Clear Actions**: Button-style visual elements for key actions
3. **Reversibility**: Can cancel before committing to processing
4. **Feedback**: Clear status messages at every step
5. **Consistency**: Similar keybindings across screens where possible
6. **Discoverability**: Footer bar shows available actions
7. **Safety**: Dangerous actions (cancel, force quit) require explicit keys

---

### Alternative Keybinding Schemes (for consideration)

**Vim-style** (for power users):
- `i` = Start recording (insert mode)
- `q` = Quit/Stop
- `w` = Write/Save
- `:q!` = Force quit

**Media Player Style**:
- `Space` = Start/Stop toggle
- `R` = Record
- `Esc` = Cancel
- `Enter` = Confirm/Save

**Recommended**: Stick with **simple, mnemonic keys** (R=Record, S=Stop, C=Cancel) for better UX.

---

### Feature 1: Cancel Recording Command

**Problem**: Currently, pressing 'q' or Ctrl+C always triggers full processing (transcription → summarization → save). There's no way to abandon an unwanted recording without creating files.

**Solution**: Add cancel command to abort recording without processing.

**Implementation**:
- Add keybinding: 'c' for cancel (or Escape)
- New `action_cancel()` method in [tui.py](src/tui.py:215)
- Skip processing worker thread entirely
- Cleanup audio files and PipeWire setup
- Show clear feedback: "❌ Recording cancelled - no files saved"
- Update UI instructions: "Press 'q' to save | 'c' to cancel"

**Use Cases**:
- False starts / accidental recordings
- Meeting cancelled or postponed
- Technical issues detected early
- Privacy concerns (realized recording shouldn't happen)

**Changes Required**:
1. Add `BINDINGS` entry for 'c' key
2. Add `action_cancel()` method
3. Update instruction text in UI
4. Add cleanup without processing logic

---

### Feature 2: Audio Format Conversion for Efficient Storage

**Problem**: Current WAV format (PCM 16-bit, 16kHz mono) is optimal for Whisper but inefficient for storage:
- ~1.8 MB per minute
- 60-minute meeting = ~108 MB
- 10 meetings = ~1 GB

**Solution**: Post-transcription conversion to compressed formats while keeping WAV during processing.

**Recommended Format: Opus** (default)
- **Compression**: 15-20 kbps for speech (90% size reduction)
- **Quality**: Superior speech quality vs MP3 at same bitrate
- **Modern**: Industry standard (WhatsApp, Discord, WebRTC)
- **Open**: Royalty-free, no licensing issues
- **Storage**: 60-min meeting = ~11 MB vs 108 MB WAV

**Alternative Format: MP3** (for compatibility)
- **Compression**: 64 kbps CBR for acceptable speech quality
- **Compatibility**: Universal playback support
- **Storage**: 60-min meeting = ~30 MB
- **Trade-off**: Less efficient, older codec

**Implementation Strategy: Post-Processing Conversion** (Option A)

**Why post-processing?**
1. Keep WAV during transcription (optimal Whisper accuracy)
2. Convert to compressed format after successful transcription
3. Delete WAV or archive based on config
4. No quality loss in transcription pipeline

**Processing Flow**:
```
1. Record → WAV (16kHz mono, existing pipeline)
2. Transcribe ← WAV (optimal quality for Whisper)
3. Transcription successful?
   ├─ Yes → Convert WAV to Opus/MP3
   │        Link compressed audio in markdown
   │        Delete WAV (if configured)
   └─ No  → Keep WAV for debugging
```

**Configuration Changes** (config.yaml):
```yaml
output:
  keep_audio: true
  audio_format: "opus"  # Options: wav, opus, mp3
  opus_bitrate: 16      # kbps (12-24 range for speech)
  mp3_bitrate: 64       # kbps (if mp3 selected)
  delete_wav_after_conversion: true  # Keep only compressed version
```

**Storage Savings** (Opus @ 16kbps):
| Meeting Length | WAV Size | Opus Size | Savings |
|----------------|----------|-----------|---------|
| 30 minutes     | 54 MB    | 5.4 MB    | 90%     |
| 60 minutes     | 108 MB   | 10.8 MB   | 90%     |
| 120 minutes    | 216 MB   | 21.6 MB   | 90%     |

**Implementation Tasks**:
1. Add ffmpeg dependency (already required)
2. Add audio conversion module (`src/audio_convert.py`)
3. Integrate conversion in processing workflow ([tui.py](src/tui.py:238) `process_recording()`)
4. Update config schema and defaults
5. Update markdown writer to link correct audio format
6. Add error handling for failed conversions (keep WAV as fallback)

**Dependencies**:
- ffmpeg (already installed for audio processing)
- Python subprocess for conversion
- No new packages required

---

## Version 0.3 - Planned Features

### Feature 1: Background Processing for Back-to-Back Meetings

**Problem**: Currently, when you stop a recording, the app blocks while processing (transcription → summarization → save). This prevents starting a new recording immediately, which is problematic for back-to-back meetings.

**Use Case**:
- 10:00-10:30 - Team Standup
- 10:30-11:00 - Product Review (starts immediately after)
- User needs to start recording the second meeting while the first is still processing

**Proposed Solution**: Asynchronous background processing queue.

**Architecture**:
```
Recording Session 1 → Stop (S)
                       ↓
                  Add to Queue
                       ↓
            ┌──────────┴──────────┐
            ↓                     ↓
    Background Worker       Return to Dashboard
    (transcribe/summarize)    (can start new recording)
            ↓
    Complete → Save
```

**Implementation Approach**:

**Option A: Background Thread Queue** (Recommended)
- Use Python `queue.Queue` and worker thread
- When user presses `S`, add recording to processing queue
- Return to dashboard immediately
- Show processing status in dashboard (e.g., "⏳ 1 recording processing...")
- Worker thread processes queue items sequentially

**Option B: Separate Process**
- Fork a separate Python process for each processing job
- More isolated but more complex
- Better for very long processing times

**Key Changes**:

1. **Processing Queue System**:
   - `ProcessingQueue` class to manage background jobs
   - Queue stores: audio_file, timestamp, title, config
   - Worker thread polls queue and processes items

2. **Dashboard Updates**:
   - Show count of recordings being processed
   - Show most recent processing status
   - Example: "⏳ Processing: 2 recordings in queue"

3. **State Management**:
   - Separate recording state from processing state
   - Can be in RECORDING state even if previous recordings are processing
   - Track multiple "jobs" independently

4. **File Management**:
   - Unique filenames prevent collisions
   - Timestamps ensure no overwrites
   - Temp directory for in-progress work

**User Workflow**:
```
1. Start Recording 1 (10:00 AM)
2. Press [S] to stop (10:30 AM)
3. → Recording 1 added to processing queue
4. → Dashboard appears immediately with "⏳ 1 recording processing..."
5. Press [R] to start Recording 2 (10:30 AM)
6. Recording 2 in progress, Recording 1 still processing in background
7. Press [S] to stop Recording 2 (11:00 AM)
8. → Recording 2 added to queue
9. → Dashboard shows "⏳ 2 recordings processing..."
10. Background worker finishes Recording 1 → saves to vault
11. Dashboard updates to "⏳ 1 recording processing..."
12. Background worker finishes Recording 2 → saves to vault
13. Dashboard shows "✅ All recordings saved"
```

**Configuration**:
```yaml
processing:
  background_mode: true  # Enable background processing
  max_concurrent: 1      # Process one at a time (sequential)
  queue_max_size: 5      # Max recordings in queue
  show_progress_in_dashboard: true
```

**Implementation Tasks**:
1. Create `ProcessingQueue` class with thread-safe queue
2. Create background worker thread that processes queue items
3. Update dashboard to show processing status
4. Modify stop_and_save action to enqueue instead of blocking
5. Add queue status widget to dashboard
6. Handle app shutdown with pending queue items (warn user)
7. Add error handling for failed processing (retry or skip)

**Benefits**:
- ✅ No waiting between back-to-back meetings
- ✅ Can record multiple meetings before any finish processing
- ✅ Better user experience for busy schedules
- ✅ Processing happens in background while you work

**Risks & Mitigations**:
| Risk | Impact | Mitigation |
|------|--------|------------|
| Resource exhaustion (multiple transcriptions) | High | Limit to sequential processing (max_concurrent: 1) |
| Queue fills up (too many pending) | Medium | Set queue_max_size, warn user when full |
| App closes with pending jobs | Medium | Warn user, ask to wait or cancel pending |
| Processing fails silently | Low | Log errors, show failed count in dashboard |

**Alternative: Simple "Continue" Option**:
- After stopping recording, show "Processing in background... Press [R] to continue or wait"
- Single background job instead of queue
- Simpler but only handles one pending recording

**Why defer to v0.3?**
- Adds significant complexity (threading, queue management)
- v0.2 focus on core UX improvements
- Need to test single-meeting workflow first
- Background processing needs careful error handling

---

## Future Enhancements (v0.4+)

### Live Transcription Display

**Goal**: Show transcription in real-time during recording, not just after stopping.

**Current State**: Transcription happens post-recording in batch mode.

**Proposed Approach**: Streaming transcription with live TUI updates.

**Implementation Options**:

**Option A: faster-whisper Streaming** (Recommended)
- Use faster-whisper's segment streaming API
- Buffer audio in small chunks (5-10 seconds)
- Process chunks in background thread
- Update TUI with partial transcripts as they arrive
- Maintain synchronized text file for crash recovery

**Architecture**:
```
PipeWire Audio → Buffer (5s chunks) → faster-whisper streaming
                                     ↓
                                  Segments
                                     ↓
                        ┌────────────┴────────────┐
                        ↓                         ↓
                    TUI Display            transcript.txt
                 (live updates)           (incremental save)
```

**Implementation Steps**:
1. Modify [transcribe.py](src/transcribe.py) to support streaming mode
2. Add audio chunking with overlap (prevent word cuts)
3. Create background worker for segment processing
4. Add scrolling transcript widget to TUI
5. Handle partial/corrected segments (Whisper refines early guesses)
6. Implement segment buffering to reduce flicker

**Challenges**:
- **Latency**: 5-10 second delay for processing (acceptable)
- **Corrections**: Later segments may correct earlier ones (need update strategy)
- **Resource usage**: Continuous model inference during recording
- **Accuracy vs speed**: May need faster model (base/small vs medium)

**Configuration**:
```yaml
whisper:
  streaming_mode: true
  chunk_duration_seconds: 5
  chunk_overlap_seconds: 0.5
  streaming_model: small  # Lighter model for real-time
```

**TUI Layout** (with live transcription):
```
╭─── Meeting Recorder ─────────────────────╮
│ 🎙️  Recording: 00:15:23                  │
│                                          │
│ Microphone:  ▓▓▓▓▓▓░░░░░  [60%]         │
│ Speakers:    ▓▓▓▓▓▓▓▓░░░  [75%]         │
│                                          │
│ ┌─ Live Transcript ────────────────────┐ │
│ │ ... and then we discussed the next   │ │
│ │ quarter's roadmap. The key priorities│ │
│ │ are feature X and bug fixes for...   │ │
│ │ [Latest text appears here]           │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ Press 'q' to save | 'c' to cancel        │
╰──────────────────────────────────────────╯
```

**Why defer to future?**
- Adds complexity to core recording pipeline
- Requires careful threading/async handling
- TUI needs scrollable text widget
- Need to tune chunking parameters for quality
- V0.1/0.2 focus: reliable recording + post-processing
- Live transcription is "nice to have" vs core requirement

**Alternative: WhisperLive Integration**
- Use actual WhisperLive library (mentioned in original plan)
- Designed specifically for streaming
- More complex setup (may need server component)
- Better latency characteristics
- Consider if faster-whisper streaming is insufficient

---

### Google Calendar Integration (Future)

**Goal**: Connect to Google Calendar to display upcoming meetings and recently recorded sessions.

**Proposed Features**:
1. **TUI Dashboard View** (before recording):
   - Show next 3-5 upcoming calendar events
   - Display 3 most recently recorded meetings with links
   - Quick meeting context awareness

2. **Auto-naming from Calendar**:
   - When starting recording, check for current/upcoming meetings
   - Auto-populate meeting title from calendar event
   - Extract attendees for metadata

3. **Post-recording Calendar Update**:
   - Optionally add transcript/summary links back to calendar event notes
   - Mark meeting as "recorded" with custom tag

**Implementation Approach**:

**Google Calendar API Integration**:
- Use Google Calendar API v3
- OAuth 2.0 authentication (one-time setup)
- Read-only access for safety (can expand to read-write later)
- Store credentials securely in config directory

**TUI Pre-recording Screen** (new mode):
```
╭─── Meeting Recorder ─────────────────────────────────────╮
│                                                           │
│  📅 Upcoming Meetings:                                    │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ • 10:00 AM - Team Standup (in 15 min)              │ │
│  │ • 11:30 AM - Product Review (in 1h 45min)          │ │
│  │ • 02:00 PM - Client Call (in 4h 15min)             │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  🎙️  Recent Recordings:                                  │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ • Team Standup - 2025-10-17 10:00  [view]          │ │
│  │ • Weekly Review - 2025-10-16 14:30  [view]         │ │
│  │ • Client Demo - 2025-10-15 11:00   [view]          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  Press 'r' to start recording | 'q' to quit              │
│                                                           │
╰───────────────────────────────────────────────────────────╯
```

**Configuration**:
```yaml
google_calendar:
  enabled: false  # Disable by default
  credentials_path: "~/.config/meeting-recorder/google-credentials.json"
  calendar_id: "primary"  # Or specific calendar ID
  upcoming_events_count: 3
  recent_recordings_count: 3
  auto_match_events: true  # Auto-name from calendar
  update_event_notes: false  # Add links back to calendar (future)
```

**Implementation Tasks**:
1. Add Google Calendar API client library (`google-api-python-client`)
2. Create OAuth setup script for initial authentication
3. Add calendar service module (`src/calendar_integration.py`)
4. Create pre-recording dashboard screen in TUI
5. Add event matching logic (time-based correlation)
6. Update markdown writer to include calendar metadata
7. Add graceful fallback when calendar unavailable

**Dependencies**:
```bash
google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

**Privacy Considerations**:
- Read-only by default (no calendar modifications)
- Local credential storage only
- Optional feature (disabled in default config)
- Clear user consent during OAuth setup

**Why defer to future?**
- Requires OAuth setup complexity
- External dependency on Google services
- V0.1/0.2 focus on core recording functionality
- Calendar integration is enhancement, not requirement
- Need to design UX flow for authentication

**Potential Enhancements**:
- Support for other calendar services (Outlook, CalDAV)
- Automatic recording triggers based on calendar events
- Meeting duration estimates from calendar
- Attendee list in meeting metadata
- Calendar event searching/filtering

---

## LLM Model Recommendation for RTX 2000 ADA (12GB VRAM)

**Your Hardware**: NVIDIA RTX 2000 ADA (12GB VRAM)
- Ada Lovelace architecture (efficient inference)
- 12GB is excellent for local LLM inference
- Enough for medium-large models with quantization

### Recommended Models (Ollama):

**Primary Recommendation: Qwen2.5:14b** (Best overall)
- **Size**: 8.7GB (fits comfortably in 12GB VRAM)
- **Quality**: Excellent instruction following and summarization
- **Speed**: ~15-25 tokens/sec on your GPU
- **Strengths**:
  - Superior structured output (perfect for your summary format)
  - Great at extracting key points, decisions, action items
  - Trained on diverse data including meeting-style content
  - Better than Llama 3.1:8b in most benchmarks

**Alternative 1: Llama 3.1:8b** (Faster, still good)
- **Size**: 4.7GB (lightweight, leaves headroom)
- **Quality**: Very good for most tasks
- **Speed**: ~30-40 tokens/sec (faster than Qwen)
- **Strengths**:
  - Well-rounded performance
  - Fast inference
  - Good instruction following
- **Use if**: You prioritize speed over quality

**Alternative 2: Mistral:7b-instruct-v0.3** (Fastest)
- **Size**: 4.1GB (very lightweight)
- **Quality**: Good for concise summaries
- **Speed**: ~40-50 tokens/sec
- **Strengths**:
  - Excellent speed
  - Concise, focused outputs
  - Low VRAM usage
- **Use if**: You want minimal processing time

**Alternative 3: Qwen2.5:7b** (Balance)
- **Size**: 4.7GB
- **Quality**: Better than Llama 3.1:8b, faster than 14b
- **Speed**: ~30-35 tokens/sec
- **Sweet spot**: Good quality without needing full 14b model

### Performance Comparison (estimated on RTX 2000 ADA):

| Model | Size | Speed (tok/s) | Quality | Recommended For |
|-------|------|---------------|---------|-----------------|
| **Qwen2.5:14b** | 8.7GB | 15-25 | ⭐⭐⭐⭐⭐ | Best summaries, worth the wait |
| Qwen2.5:7b | 4.7GB | 30-35 | ⭐⭐⭐⭐ | Good balance |
| Llama 3.1:8b | 4.7GB | 30-40 | ⭐⭐⭐⭐ | Reliable, fast |
| Mistral:7b | 4.1GB | 40-50 | ⭐⭐⭐ | Speed priority |

### My Recommendation: **Qwen2.5:14b**

**Why?**
1. **Quality**: Noticeably better at structured outputs (your use case)
2. **Fit**: 8.7GB fits well in 12GB with room for overhead
3. **Worth the wait**: 30-60 sec summary time vs 15-30 sec is acceptable for quality gain
4. **Specialization**: Excellent at extracting decisions/action items from conversations

**Typical Summary Time** (60-min meeting transcript):
- Qwen2.5:14b: ~30-45 seconds
- Llama 3.1:8b: ~20-30 seconds
- Mistral:7b: ~15-25 seconds

Since summarization happens after the meeting (not real-time), the extra 15-20 seconds for significantly better quality is worth it.

### Updated Config Recommendation:

```yaml
summarization:
  ollama_endpoint: "http://localhost:11434"
  model: "qwen2.5:14b"  # Best quality for your 12GB GPU
  # Alternative options:
  # model: "llama3.1:8b"    # Faster, still good
  # model: "qwen2.5:7b"     # Good balance
  # model: "mistral:7b"     # Maximum speed
```

### Installation:
```bash
# Pull the recommended model
ollama pull qwen2.5:14b

# Or try alternatives
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
```

**Test it out**: Run a few test summaries with different models and see which quality/speed trade-off you prefer. Your hardware can handle any of them comfortably.

---

## Resources

- WhisperLive: https://github.com/collabora/WhisperLive
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Ollama: https://ollama.ai
- Ollama Model Library: https://ollama.ai/library
- PipeWire: https://wiki.archlinux.org/title/PipeWire
- Textual (TUI framework): https://textual.textualize.io
- ffmpeg documentation: https://ffmpeg.org/documentation.html
