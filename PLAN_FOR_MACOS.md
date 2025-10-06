# Meeting Recorder - macOS Port Implementation Plan

## Overview

This document outlines the plan to port the Meeting Recorder TUI from Linux (PipeWire) to macOS using a **hybrid Swift + Python architecture**. The goal is to achieve a "Granola-like" experience: single-command execution with no external audio driver dependencies.

## Executive Summary

**Approach**: Hybrid architecture separating concerns by platform capabilities
- **Swift binary**: Native audio capture (system + microphone) using Core Audio Tap API
- **Python codebase**: Existing transcription, summarization, TUI, and file output (95% reusable)
- **Integration**: Swift pipes raw PCM audio to stdout → Python reads from stdin
- **Distribution**: Single `.app` bundle or bootstrap script

**Timeline Estimate**: 2-3 days for hybrid implementation

**Future Path**: Evaluate full Swift rewrite after validating hybrid approach

## Why Hybrid Architecture?

### Advantages ✅
- **Leverage existing code**: Keep all Python logic (transcription, LLM, TUI, Obsidian output)
- **Native audio performance**: Use macOS-optimized APIs without compromises
- **No external drivers**: Use ScreenCaptureKit/Core Audio Tap API (macOS 13+)
- **Minimal changes**: ~50 LOC changes in Python, ~250 LOC new Swift code
- **Fast iteration**: Test audio capture independently from transcription pipeline

### Trade-offs ⚖️
- Two languages to maintain (vs. pure Python or pure Swift)
- Inter-process communication via pipes (minimal overhead)
- Requires Xcode for building Swift binary (one-time, can distribute compiled)

## macOS Audio Landscape

### Native APIs Available (No Driver Required)

1. **Core Audio Tap API** (macOS 14.2+)
   - Captures system audio output from all or specific processes
   - Requires user permission (like screen recording)
   - **Recommended for system audio**

2. **ScreenCaptureKit** (macOS 13+)
   - Originally for screen capture, supports audio streams
   - Can capture system audio + microphone (macOS 15+ for mic)
   - More complex API, designed for video workflows

3. **AVAudioEngine** (All versions)
   - Standard microphone capture
   - **Recommended for microphone input**

### Chosen Approach

**Hybrid using Core Audio Tap + AVAudioEngine**:
- Core Audio Tap for system audio (simple, focused API)
- AVAudioEngine for microphone (well-documented, stable)
- Mix both streams in Swift, output to stdout as raw PCM
- Similar to how [AudioTee](https://github.com/makeusabrew/audiotee) works

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────┐
│  Swift CLI: audio-capture                       │
│  ┌───────────────────────────────────────────┐  │
│  │  Core Audio Tap → System Audio            │  │
│  │  AVAudioEngine  → Microphone              │  │
│  │  Audio Mixer    → Combined PCM stream     │  │
│  └───────────────────┬───────────────────────┘  │
│                      │ stdout (raw PCM)         │
└──────────────────────┼──────────────────────────┘
                       │ pipe
┌──────────────────────▼──────────────────────────┐
│  Python: meeting-recorder                       │
│  ┌───────────────────────────────────────────┐  │
│  │  Read stdin → faster-whisper transcription│  │
│  │  Ollama → Summarization                   │  │
│  │  Textual → TUI with audio levels          │  │
│  │  File Writer → Obsidian markdown output   │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Component Breakdown

#### Swift Binary: `audio-capture`

**Responsibilities**:
- Enumerate and select audio devices
- Capture system audio via Core Audio Tap API
- Capture microphone via AVAudioEngine
- Mix both streams to mono PCM (16kHz, 16-bit signed, little-endian)
- Write raw audio to stdout continuously
- Handle start/stop signals (SIGINT, SIGTERM)
- Minimal error output to stderr

**Public Interface** (command-line):
```bash
audio-capture [OPTIONS]

Options:
  --sample-rate RATE    Sample rate in Hz (default: 16000)
  --mic-device NAME     Microphone device name (default: system default)
  --system-audio        Enable system audio capture (default: true)
  --microphone          Enable microphone capture (default: true)
  --format FORMAT       Output format: s16le (default)
  --help                Show help message

Output:
  - Writes raw PCM audio to stdout (continuous stream)
  - Status/error messages to stderr
  - Exit codes: 0 (success), 1 (error), 2 (permission denied)
```

**Example Usage**:
```bash
# Capture system audio + mic, output to stdout
./audio-capture --sample-rate 16000 | python process_audio.py

# Test audio capture by piping to a file
./audio-capture > test_audio.raw
```

**Key Swift Classes**:
```swift
// Main coordinator
class AudioCaptureManager {
    var systemAudioTap: SystemAudioCapture?
    var microphoneCapture: MicrophoneCapture?
    var mixer: AudioMixer
    var outputWriter: StdoutWriter

    func start() throws
    func stop()
}

// System audio via Core Audio Tap
class SystemAudioCapture {
    func setupTap() throws -> CATapDescription
    func startCapture(callback: (AudioBuffer) -> Void)
}

// Microphone via AVAudioEngine
class MicrophoneCapture {
    let audioEngine = AVAudioEngine()
    func startCapture(callback: (AudioBuffer) -> Void)
}

// Mix and format audio
class AudioMixer {
    func mix(systemBuffer: AudioBuffer?, micBuffer: AudioBuffer?) -> Data
    func resample(to sampleRate: Int)
}

// Write to stdout
class StdoutWriter {
    func write(_ data: Data)
}
```

**Estimated Size**: ~250-300 lines of Swift code

#### Python Integration Changes

**File: `src/audio_setup.py`**
- Add macOS detection: `platform.system() == "Darwin"`
- If macOS, skip PipeWire setup
- Launch Swift binary as subprocess: `subprocess.Popen(['./audio-capture'])`
- Return process handle for cleanup

**File: `src/transcribe.py`**
- Replace `parec` command with reading from subprocess stdout
- Change from:
  ```python
  self.recording_process = subprocess.Popen(["parec", "--device", source_name, ...])
  ```
- To:
  ```python
  if platform.system() == "Darwin":
      self.recording_process = subprocess.Popen(
          ["./audio-capture", "--sample-rate", "16000"],
          stdout=subprocess.PIPE
      )
      audio_stream = self.recording_process.stdout
  else:
      # Existing Linux/PipeWire code
  ```

**File: `src/audio_monitor.py`**
- macOS alternative: Parse audio levels from Swift stderr output
- Or: Disable real-time monitoring on macOS initially (MVP)
- Future: Implement simple RMS calculation in Python from stdin

**File: `meeting-recorder` (launcher)**
- Detect OS, set appropriate paths
- Ensure Swift binary is executable and in correct location

**Estimated Changes**: ~50-100 lines of Python modifications

### Packaging Structure

#### Option A: .app Bundle (Native macOS)

```
MeetingRecorder.app/
├── Contents/
│   ├── Info.plist                    # App metadata, permissions
│   ├── MacOS/
│   │   ├── audio-capture            # Swift binary (compiled)
│   │   └── meeting-recorder         # Python entry point (PyInstaller bundled)
│   └── Resources/
│       ├── config.yaml              # Default configuration
│       ├── icon.icns                # App icon
│       └── python_modules/          # Bundled Python libraries
│           ├── faster_whisper/
│           ├── textual/
│           └── ...
```

**Launch**: Double-click `MeetingRecorder.app` or `open MeetingRecorder.app` from terminal

**Permissions** (in `Info.plist`):
```xml
<key>NSMicrophoneUsageDescription</key>
<string>Meeting Recorder needs access to your microphone to transcribe your speech.</string>

<key>NSAudioCaptureUsageDescription</key>
<string>Meeting Recorder needs to capture system audio for meeting transcription.</string>
```

#### Option B: Bootstrap Script (Simpler Initial Approach)

```
meeting-recorder-macos/
├── bin/
│   ├── audio-capture                # Compiled Swift binary
│   └── meeting-recorder             # Bash launcher script
├── src/
│   └── (Python source files)
├── venv/                            # Python virtual environment
├── config.yaml
└── README_MACOS.md
```

**Launcher Script** (`meeting-recorder`):
```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$SCRIPT_DIR/bin:$PATH"
source "$SCRIPT_DIR/venv/bin/activate"
python3 "$SCRIPT_DIR/src/tui.py"
```

**Pros**: Easier to debug, faster iteration
**Cons**: Less polished, requires terminal

**Recommendation**: Start with Option B (bootstrap), migrate to Option A (`.app` bundle) after validation

## Implementation Phases

### Phase 1: Swift Audio Capture CLI (Days 1-2)

**Goal**: Build standalone Swift binary that captures system + mic audio and outputs to stdout

**Tasks**:
1. **Project Setup**
   - Create Swift command-line project: `swift package init --type executable`
   - Add dependencies: None required (Foundation + AVFoundation + CoreAudio are built-in)
   - Configure build settings (macOS 13+ deployment target)

2. **Implement Core Audio Tap Capture**
   - Request audio capture permission
   - Create tap on default output device
   - Handle audio buffers in callback
   - Convert to PCM format (16kHz, mono, s16le)
   - Research: Use AudioTee as reference implementation

3. **Implement Microphone Capture**
   - Set up AVAudioEngine
   - Configure input node for default microphone
   - Install tap on microphone bus
   - Match format to system audio (16kHz, mono)

4. **Audio Mixing**
   - Synchronize system + mic streams (timestamps)
   - Mix buffers (simple addition with normalization)
   - Output single PCM stream to stdout

5. **Command-Line Interface**
   - Parse arguments (sample rate, device selection, enable/disable sources)
   - Signal handling (SIGINT, SIGTERM for clean shutdown)
   - Error messages to stderr

**Testing**:
```bash
# Test 1: Capture 10 seconds of audio to file
./audio-capture > test.raw
# Verify with: ffplay -f s16le -ar 16000 -ac 1 test.raw

# Test 2: Real-time playback (sanity check)
./audio-capture | ffplay -f s16le -ar 16000 -ac 1 -

# Test 3: Check for audio gaps or corruption
./audio-capture | python -c "
import sys
data = sys.stdin.buffer.read()
print(f'Captured {len(data)} bytes')
print(f'Duration: {len(data) / (16000 * 2)} seconds')
"
```

**Deliverables**:
- `audio-capture` compiled binary (~50-100 KB)
- Source code in `macos/swift/AudioCapture/`
- Basic README with build instructions

**Validation Criteria**:
- ✅ Audio plays back correctly without gaps
- ✅ System audio and microphone both captured
- ✅ Output format matches expected PCM spec
- ✅ Runs for >5 minutes without crashes
- ✅ Clean shutdown on Ctrl+C

### Phase 2: Python Integration (Day 2)

**Goal**: Modify Python codebase to read from Swift binary instead of PipeWire

**Tasks**:
1. **Platform Detection**
   - Add `platform.system()` checks in audio modules
   - Create `src/audio_setup_macos.py` for macOS-specific logic
   - Keep Linux code unchanged (use conditional imports)

2. **Update `src/transcribe.py`**
   - Replace `parec` subprocess with `audio-capture` subprocess
   - Read from `process.stdout` instead of audio file handle
   - Handle process lifecycle (start, monitor, stop)

3. **Update `src/audio_monitor.py`**
   - Option 1: Disable real-time level display on macOS (MVP)
   - Option 2: Calculate RMS from audio stream in Python
   - Document limitation in README if needed

4. **Update Launcher Script**
   - Detect macOS vs. Linux
   - Set correct binary paths
   - Check for Swift binary before starting

5. **Configuration Updates**
   - Add `macos` section to `config.yaml`:
     ```yaml
     macos:
       audio_capture_binary: "./bin/audio-capture"
       enable_system_audio: true
       enable_microphone: true
     ```

**Testing**:
```bash
# Integration test: Record 30 seconds and transcribe
./meeting-recorder
# Speak into microphone + play system audio
# Press 'q' after 30 seconds
# Verify transcript contains both sources

# Test 2: Long session (5+ minutes)
./meeting-recorder
# Let it run, check for memory leaks or crashes

# Test 3: Graceful shutdown
./meeting-recorder
# Press Ctrl+C immediately after start
# Verify cleanup happens correctly
```

**Deliverables**:
- Modified Python source files with macOS support
- Updated `config.yaml` with macOS defaults
- `README_MACOS.md` with setup instructions

**Validation Criteria**:
- ✅ Transcription works end-to-end on macOS
- ✅ No regressions on Linux (test both platforms)
- ✅ Clean error messages if Swift binary missing
- ✅ Graceful shutdown cleans up processes

### Phase 3: App Bundle Packaging (Day 3)

**Goal**: Package as single-command distribution (`.app` or polished script)

**Tasks**:
1. **PyInstaller Bundling**
   - Create `meeting-recorder.spec` file for PyInstaller
   - Bundle Python code + dependencies into executable
   - Test bundled version works standalone

2. **Create .app Bundle Structure**
   - Generate `Info.plist` with correct permissions
   - Copy Swift binary to `Contents/MacOS/`
   - Copy Python bundle to `Contents/MacOS/`
   - Add icon (`icon.icns`)

3. **Build Script**
   - Automate: Swift compile → PyInstaller → .app assembly
   - Example: `./build_macos.sh` script
   - Produce distributable `.app` or `.zip`

4. **Code Signing (Optional but Recommended)**
   - Sign Swift binary: `codesign -s "Developer ID" audio-capture`
   - Sign .app bundle: `codesign -s "Developer ID" MeetingRecorder.app`
   - Create DMG for distribution (optional)

**Testing**:
```bash
# Test 1: Double-click .app in Finder
# Verify it launches and prompts for permissions

# Test 2: Run from terminal
open MeetingRecorder.app

# Test 3: Test on clean macOS VM (no dev tools)
# Verify it runs without Xcode/Python installed
```

**Deliverables**:
- `MeetingRecorder.app` bundle
- `build_macos.sh` build script
- `README_DISTRIBUTION.md` with user instructions

**Validation Criteria**:
- ✅ Single-command launch works
- ✅ Permissions prompts appear correctly
- ✅ No dependency on system Python or Xcode
- ✅ Works on fresh macOS install (13+)

### Phase 4: Testing & Documentation (Day 3)

**Goal**: Validate reliability and document usage

**Tasks**:
1. **End-to-End Testing**
   - Real meeting recording (30+ minutes)
   - Verify transcription accuracy
   - Check summary quality
   - Confirm Obsidian files written correctly

2. **Edge Case Testing**
   - No microphone connected
   - No system audio playing
   - Stop immediately after start
   - Stop during transcription
   - Invalid Obsidian path

3. **Performance Testing**
   - CPU usage during recording
   - Memory usage over time
   - Disk space requirements
   - Processing time (transcription + summarization)

4. **Documentation**
   - Update `README.md` with macOS section
   - Create `INSTALL_MACOS.md` with step-by-step setup
   - Document known limitations
   - Add troubleshooting section

**Deliverables**:
- Test results document
- Updated README with macOS instructions
- Known issues list

**Validation Criteria**:
- ✅ 30+ minute meeting records successfully
- ✅ All edge cases handled gracefully
- ✅ Documentation covers first-time user setup
- ✅ Performance acceptable (not worse than Linux version)

## Technical Details

### Audio Format Specification

**PCM Configuration** (must match between Swift and Python):
- **Sample Rate**: 16,000 Hz (optimal for Whisper)
- **Bit Depth**: 16-bit signed integer
- **Channels**: 1 (mono)
- **Byte Order**: Little-endian
- **Format String**: `s16le` (signed 16-bit little-endian)

**Data Rate**: 16,000 samples/sec × 2 bytes/sample × 1 channel = **32 KB/sec**

**Buffer Size**: 200ms chunks (similar to AudioTee)
- Buffer: 16,000 × 0.2 = 3,200 samples
- Bytes per buffer: 3,200 × 2 = 6,400 bytes

### Swift Implementation Patterns

#### Error Handling
```swift
enum AudioCaptureError: Error {
    case permissionDenied
    case deviceNotFound
    case tapCreationFailed
    case audioEngineError(String)
}

// Usage
do {
    try audioManager.start()
} catch AudioCaptureError.permissionDenied {
    fputs("ERROR: Audio capture permission denied. Please grant access in System Settings.\n", stderr)
    exit(2)
} catch {
    fputs("ERROR: \(error.localizedDescription)\n", stderr)
    exit(1)
}
```

#### Permission Requests
```swift
import AVFoundation

func requestMicrophonePermission() async -> Bool {
    await AVCaptureDevice.requestAccess(for: .audio)
}

// For Core Audio Tap, permission is automatic (same as screen recording)
// Add NSAudioCaptureUsageDescription to Info.plist
```

#### Signal Handling
```swift
import Foundation

var shouldStop = false

signal(SIGINT) { _ in
    shouldStop = true
}

signal(SIGTERM) { _ in
    shouldStop = true
}

// Main loop
while !shouldStop {
    // Process audio
}

audioManager.stop()
```

### Python Integration Patterns

#### Subprocess Management
```python
import subprocess
import platform

class AudioCaptureSetup:
    def __init__(self):
        self.is_macos = platform.system() == "Darwin"
        self.audio_process = None

    def setup(self):
        if self.is_macos:
            return self._setup_macos()
        else:
            return self._setup_linux()

    def _setup_macos(self):
        # Launch Swift binary
        binary_path = Path(__file__).parent.parent / "bin" / "audio-capture"

        if not binary_path.exists():
            raise FileNotFoundError(f"Audio capture binary not found: {binary_path}")

        self.audio_process = subprocess.Popen(
            [str(binary_path), "--sample-rate", "16000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # Unbuffered
        )

        return self.audio_process.stdout

    def cleanup(self):
        if self.audio_process:
            self.audio_process.terminate()
            self.audio_process.wait(timeout=5)
```

#### Reading Audio Stream
```python
def start_recording(self):
    if self.is_macos:
        # Read from subprocess stdout
        audio_stream = self.audio_capture.setup()

        # Read in chunks
        while self.running:
            chunk = audio_stream.read(6400)  # 200ms buffer
            if not chunk:
                break
            self.audio_file_handle.write(chunk)
    else:
        # Existing Linux code
        pass
```

### Cross-Platform Configuration

**config.yaml**:
```yaml
# Platform-agnostic settings
audio:
  sample_rate: 16000
  format: s16le
  channels: 1

# Platform-specific overrides
linux:
  audio_backend: pipewire

macos:
  audio_capture_binary: "./bin/audio-capture"
  enable_system_audio: true
  enable_microphone: true
  # Optional: specify devices
  # microphone_device: "Built-in Microphone"
```

**Loading configuration**:
```python
import platform
import yaml

def load_config():
    with open('config.yaml') as f:
        config = yaml.safe_load(f)

    platform_key = 'macos' if platform.system() == 'Darwin' else 'linux'
    platform_config = config.get(platform_key, {})

    # Merge platform-specific config
    config['audio'].update(platform_config)

    return config
```

## Build & Distribution

### Development Build

**Swift Binary**:
```bash
cd macos/swift/AudioCapture
swift build -c release
cp .build/release/audio-capture ../../../bin/
```

**Python Setup**:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Run**:
```bash
./meeting-recorder
```

### Release Build Script

**build_macos.sh**:
```bash
#!/bin/bash
set -e

echo "Building Meeting Recorder for macOS..."

# Build Swift binary
echo "1. Compiling Swift audio capture binary..."
cd macos/swift/AudioCapture
swift build -c release
cd ../../..
cp macos/swift/AudioCapture/.build/release/audio-capture bin/

# Bundle Python with PyInstaller
echo "2. Bundling Python application..."
source venv/bin/activate
pyinstaller meeting-recorder.spec

# Create .app bundle
echo "3. Creating .app bundle..."
mkdir -p "MeetingRecorder.app/Contents/MacOS"
mkdir -p "MeetingRecorder.app/Contents/Resources"

cp bin/audio-capture "MeetingRecorder.app/Contents/MacOS/"
cp dist/meeting-recorder "MeetingRecorder.app/Contents/MacOS/"
cp macos/Info.plist "MeetingRecorder.app/Contents/"
cp macos/icon.icns "MeetingRecorder.app/Contents/Resources/"

# Sign (optional, requires Developer ID)
if [ -n "$CODESIGN_IDENTITY" ]; then
    echo "4. Signing application..."
    codesign -s "$CODESIGN_IDENTITY" "MeetingRecorder.app/Contents/MacOS/audio-capture"
    codesign -s "$CODESIGN_IDENTITY" "MeetingRecorder.app"
fi

echo "Done! MeetingRecorder.app created."
```

### Distribution Options

**Option 1: GitHub Release**
- Upload `MeetingRecorder.app.zip`
- Include `README_MACOS.md` with installation instructions
- Tag releases: `v0.1.0-macos`

**Option 2: Homebrew Cask** (future)
```ruby
cask "meeting-recorder" do
  version "0.1.0"
  sha256 "..."

  url "https://github.com/user/meeting-recorder/releases/download/v#{version}/MeetingRecorder.app.zip"
  name "Meeting Recorder"
  desc "Local-first meeting transcription tool"

  app "MeetingRecorder.app"
end
```

**Option 3: DMG Installer** (polished)
- Use `create-dmg` tool
- Add drag-to-Applications shortcut
- Background image with instructions

## Testing Strategy

### Unit Tests (Swift)

**Test Audio Format Conversion**:
```swift
import XCTest

class AudioMixerTests: XCTestCase {
    func testPCMFormatConversion() {
        let mixer = AudioMixer(sampleRate: 16000)
        let testBuffer = generateTestTone(frequency: 440, duration: 1.0)

        let pcmData = mixer.convertToPCM(testBuffer)

        XCTAssertEqual(pcmData.count, 16000 * 2) // 16kHz * 2 bytes
        XCTAssertTrue(isPCMS16LE(pcmData))
    }

    func testMixingBuffers() {
        let mixer = AudioMixer(sampleRate: 16000)
        let buffer1 = generateTestTone(frequency: 440, duration: 0.2)
        let buffer2 = generateTestTone(frequency: 880, duration: 0.2)

        let mixed = mixer.mix(systemBuffer: buffer1, micBuffer: buffer2)

        XCTAssertEqual(mixed.count, 3200 * 2) // 200ms at 16kHz
        XCTAssertFalse(mixed.allSatisfy { $0 == 0 }) // Not silent
    }
}
```

### Integration Tests (Python)

**Test Swift Binary Communication**:
```python
import subprocess
import time

def test_audio_capture_binary():
    """Test that Swift binary runs and outputs data"""
    proc = subprocess.Popen(
        ['./bin/audio-capture', '--sample-rate', '16000'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    time.sleep(2)  # Capture for 2 seconds

    # Read some data
    data = proc.stdout.read(32000)  # 1 second of audio
    assert len(data) == 32000

    # Terminate
    proc.terminate()
    proc.wait()
    assert proc.returncode == 0 or proc.returncode == -15  # SIGTERM

def test_end_to_end_transcription():
    """Test full pipeline on macOS"""
    transcriber = Transcriber(model_size="tiny", device="cpu")
    transcriber.load_model()

    # Start recording (will use Swift binary on macOS)
    transcriber.start_recording("default")

    # Simulate meeting (play test audio)
    subprocess.run(['say', 'This is a test of the meeting recorder'])
    time.sleep(5)

    transcriber.stop_recording()

    # Transcribe
    transcript = transcriber.transcribe_audio(transcriber.audio_file)

    assert 'test' in transcript.lower()
    assert transcriber.transcript_file.exists()
```

### Manual Testing Checklist

**Initial Setup**:
- [ ] Fresh macOS 13.0+ install (VM or physical)
- [ ] No developer tools installed
- [ ] Ollama installed and running

**Installation**:
- [ ] Download `.app` bundle
- [ ] Double-click to launch
- [ ] Grant microphone permission
- [ ] Grant audio capture permission
- [ ] App launches TUI successfully

**Recording**:
- [ ] Start recording shows timer
- [ ] Speak into microphone → should capture
- [ ] Play YouTube video → should capture system audio
- [ ] Audio levels display (if implemented)
- [ ] Press 'q' → stops cleanly
- [ ] Ctrl+C → stops cleanly

**Processing**:
- [ ] Transcription completes without errors
- [ ] Transcript file created in Obsidian vault
- [ ] Transcript contains spoken words
- [ ] Transcript contains system audio (e.g., video dialogue)
- [ ] Summary generated
- [ ] Summary file created with correct format

**Edge Cases**:
- [ ] No microphone connected → graceful error
- [ ] Obsidian path doesn't exist → creates directory
- [ ] Ollama not running → clear error message
- [ ] Stop immediately after start → cleans up correctly
- [ ] 60+ minute recording → no crashes, good performance

**Performance**:
- [ ] CPU usage during recording <50% (on M1/M2/M3)
- [ ] Memory usage <500 MB during recording
- [ ] No audio dropouts or glitches
- [ ] Transcription time ~1-2x real-time

## Known Limitations & Mitigation

| Limitation | Impact | Mitigation | Future Fix |
|------------|--------|------------|------------|
| Requires macOS 13+ | Can't run on older macOS | Document minimum version clearly | None (old OS unsupported by Apple) |
| Two binaries (Swift + Python) | More complex packaging | Bundle both in .app | Full Swift rewrite (Phase 2 evaluation) |
| No real-time audio levels (MVP) | Less visual feedback | Show recording status instead | Calculate RMS in Python from stream |
| Microphone echo in system audio | May capture own voice twice | Document limitation, use headphones | Investigate echo cancellation in Swift |
| Swift binary requires Xcode to build | Contributors need Xcode | Provide pre-compiled binary | CI/CD auto-build on GitHub Actions |
| Permission prompts | First-time friction | Clear instructions in README | Use entitlements to improve UX |

## Migration Path to Full Swift (Phase 2)

**When to Consider**:
- Hybrid approach validated and working
- User feedback indicates need for native features (e.g., system tray, Shortcuts integration)
- Maintenance burden of two languages becomes significant
- Performance improvements needed

**Effort Estimate**: 1-2 weeks full-time

**Components to Rewrite**:
1. **TUI** → SwiftUI or Vapor (TUI library)
2. **Transcription** → Swift bindings for faster-whisper (whisper.cpp already has Swift examples)
3. **Summarization** → HTTP client to Ollama (simple `URLSession` calls)
4. **File Output** → Swift `FileManager` (trivial)

**Advantages of Full Swift**:
- Single language, simpler distribution
- Native macOS integrations (Shortcuts, Continuity, etc.)
- Potentially better performance
- System tray icon, background recording

**Disadvantages**:
- Lose Python ML ecosystem (harder to swap models/libraries)
- More complex code (Swift is verbose)
- Fewer contributors (smaller Swift ecosystem vs. Python)

**Recommendation**: Stick with hybrid unless clear need arises

## Success Criteria

**MVP (Minimum Viable Product)**:
- [x] Single-command launch: `./meeting-recorder` or double-click `.app`
- [x] Records system audio + microphone without external drivers
- [x] Transcription works accurately (>90% for clear speech)
- [x] Summary generated with structured format
- [x] Files saved to Obsidian vault correctly
- [x] Works on macOS 13+
- [x] Graceful shutdown on 'q' or Ctrl+C

**Quality Targets**:
- [x] Setup time <10 minutes for new user
- [x] No crashes during 60-minute recording
- [x] Transcription time <2x real-time
- [x] CPU usage <50% during recording (M1/M2)
- [x] Clear error messages for all failure modes

## Resources

### Reference Implementations
- **AudioTee**: https://github.com/makeusabrew/audiotee (Core Audio Tap example)
- **Azayaka**: https://github.com/Mnpn/Azayaka (ScreenCaptureKit screen recorder with audio)
- **AudioCap**: https://github.com/insidegui/AudioCap (Core Audio Tap sample code)

### Documentation
- **Core Audio Tap API**: https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps
- **AVAudioEngine**: https://developer.apple.com/documentation/avfaudio/avaudioengine
- **PyInstaller macOS**: https://pyinstaller.org/en/stable/usage.html#macos
- **App Bundle Structure**: https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFBundles/BundleTypes/BundleTypes.html

### Tools
- **Xcode**: Required for compiling Swift code
- **PyInstaller**: Python bundling tool
- **create-dmg**: DMG creation tool (https://github.com/create-dmg/create-dmg)
- **ffmpeg/ffplay**: Audio testing and playback

## Next Steps

1. **Immediate**: Set up Swift project structure, implement basic Core Audio Tap capture
2. **Day 1**: Complete Swift audio capture binary with tests
3. **Day 2**: Integrate with Python codebase, test end-to-end
4. **Day 3**: Package as `.app` bundle, create distribution
5. **Post-MVP**: Gather user feedback, evaluate full Swift rewrite

## Appendix: Example Code Snippets

### Swift: Core Audio Tap Setup

```swift
import CoreAudio
import AVFoundation

class SystemAudioCapture {
    private var tapDescription: CATapDescription?

    func setupTap() throws {
        // Get default output device
        var deviceID = AudioDeviceID()
        var propertySize = UInt32(MemoryLayout<AudioDeviceID>.size)
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &propertyAddress,
            0,
            nil,
            &propertySize,
            &deviceID
        )

        guard status == noErr else {
            throw AudioCaptureError.deviceNotFound
        }

        // Create tap description
        let tapDesc = CATapDescription(
            processes: [],  // Empty = all processes
            isExclusive: true,
            isMuted: false,
            sampleRate: 16000.0
        )

        // Create tap
        var tap: CATap?
        let tapStatus = AudioHardwareCreateProcessTap(
            deviceID,
            tapDesc,
            &tap
        )

        guard tapStatus == noErr, let tap = tap else {
            throw AudioCaptureError.tapCreationFailed
        }

        self.tapDescription = tapDesc

        // Start receiving audio
        AudioHardwareStartProcessTap(tap) { audioBuffer in
            self.handleAudioBuffer(audioBuffer)
        }
    }

    private func handleAudioBuffer(_ buffer: AudioBuffer) {
        // Process audio buffer
        // Convert to PCM, send to mixer
    }
}
```

### Swift: Microphone Capture with AVAudioEngine

```swift
import AVFoundation

class MicrophoneCapture {
    private let audioEngine = AVAudioEngine()
    private var mixer: AudioMixer

    func startCapture() throws {
        let inputNode = audioEngine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        // Configure for 16kHz mono
        let recordingFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: 16000,
            channels: 1,
            interleaved: false
        )

        guard let recordingFormat = recordingFormat else {
            throw AudioCaptureError.audioEngineError("Failed to create format")
        }

        // Install tap
        inputNode.installTap(onBus: 0, bufferSize: 3200, format: inputFormat) { buffer, time in
            // Convert to 16kHz mono
            let convertedBuffer = self.convertBuffer(buffer, to: recordingFormat)
            self.mixer.addMicrophoneBuffer(convertedBuffer)
        }

        audioEngine.prepare()
        try audioEngine.start()
    }

    func stop() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
    }
}
```

### Python: Platform Detection and Audio Setup

```python
import platform
import subprocess
from pathlib import Path

class AudioCaptureSetup:
    def __init__(self):
        self.platform = platform.system()
        self.audio_process = None

    def setup(self) -> bool:
        if self.platform == "Darwin":
            return self._setup_macos()
        elif self.platform == "Linux":
            return self._setup_linux()
        else:
            raise RuntimeError(f"Unsupported platform: {self.platform}")

    def _setup_macos(self) -> bool:
        """Setup audio capture on macOS using Swift binary"""
        binary_path = Path(__file__).parent.parent / "bin" / "audio-capture"

        if not binary_path.exists():
            print(f"Error: Audio capture binary not found at {binary_path}")
            print("Please run build_macos.sh to compile the Swift binary.")
            return False

        try:
            self.audio_process = subprocess.Popen(
                [str(binary_path), "--sample-rate", "16000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )

            print("macOS audio capture started")
            return True

        except Exception as e:
            print(f"Error starting audio capture: {e}")
            return False

    def _setup_linux(self) -> bool:
        """Setup audio capture on Linux using PipeWire"""
        # Existing PipeWire logic
        pass

    def get_audio_stream(self):
        """Return audio stream for reading"""
        if self.platform == "Darwin":
            return self.audio_process.stdout
        else:
            return self.get_monitor_source()  # Linux PipeWire

    def cleanup(self):
        """Cleanup audio capture resources"""
        if self.platform == "Darwin" and self.audio_process:
            self.audio_process.terminate()
            self.audio_process.wait(timeout=5)
            print("macOS audio capture stopped")
        else:
            # Existing Linux cleanup
            pass
```

---

**Document Version**: 1.0
**Last Updated**: 2025-10-06
**Status**: Ready for Implementation
