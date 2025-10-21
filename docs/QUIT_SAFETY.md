# Quit Safety Feature

## Problem

Previously, users could press `Q` to quit the application even while recordings were being processed in the background. This would cause:
- Loss of in-progress transcriptions
- Loss of pending jobs in the queue
- No warning to the user

## Solution

Added intelligent quit handling with three levels of safety:

### 1. Recording in Progress
If user presses `Q` while recording:
- Automatically cancels the recording
- Returns to dashboard (doesn't exit immediately)
- User can press `Q` again to quit if desired

### 2. Jobs Processing/Pending
If user presses `Q` while jobs are in queue:
```
⚠️  Warning: Processing in Progress

1 job(s) currently processing
2 job(s) pending

Options:
  [W] Wait for completion (recommended)
  [F] Force quit (will lose progress)
  [Esc] Cancel and return

Press your choice...
```

**Options:**
- **[W] Wait**: Waits for all jobs to complete, then exits cleanly
- **[F] Force quit**: Immediately exits, abandoning jobs
- **[Esc] Cancel**: Returns to dashboard, keeps processing

### 3. No Jobs Active
If no recording or processing is happening:
- Exits immediately (safe)

## Implementation Details

### Key Methods

**`action_quit_app()`**
- Checks recording state
- Checks processing queue status
- Shows warning if jobs active
- Enters quit confirmation mode

**`_shutdown_and_exit()`**
- Stops processing queue (wait=False for force quit)
- Exits application

**`on_key()` handler**
- Handles W/F/Esc during quit confirmation
- Priority: quit confirmation → title editing → normal keys

### State Management

Uses `self._quit_confirmation` flag to track when user is in quit confirmation mode. This ensures keypresses are routed correctly.

## User Experience

### Before (v0.4)
```
User: *presses Q while processing*
App: *exits immediately*
User: "Where did my recording go?"
```

### After (v0.4.1)
```
User: *presses Q while processing*
App: "⚠️  Warning: Processing in Progress... [W]ait, [F]orce quit, [Esc]ape"
User: *presses W*
App: "⏳ Waiting for jobs to complete..."
App: *completes processing, then exits*
User: "Great, my recording is safe!"
```

## Edge Cases Handled

1. **Recording + Processing**: Cancels recording first, then shows processing warning
2. **Multiple pending jobs**: Shows total count in warning
3. **Ctrl+C during wait**: User can still force quit if needed
4. **Quick double-Q**: First Q cancels recording, second Q shows processing warning

## Testing

### Test Case 1: Quit During Recording
1. Start recording
2. Press `Q`
3. **Expected**: Recording canceled, returned to dashboard
4. Press `Q` again
5. **Expected**: Exits (no jobs in progress)

### Test Case 2: Quit During Processing
1. Record a meeting
2. Stop recording (starts processing)
3. Immediately press `Q`
4. **Expected**: Warning shown with job count
5. Press `W`
6. **Expected**: Waits for processing, then exits

### Test Case 3: Quit with Multiple Jobs
1. Record meeting 1, stop (starts processing)
2. Record meeting 2, stop (queues second job)
3. Press `Q`
4. **Expected**: "1 processing, 1 pending"
5. Press `Esc`
6. **Expected**: Returns to dashboard, processing continues

### Test Case 4: Force Quit
1. Record a meeting, stop (starts processing)
2. Press `Q`
3. Press `F`
4. **Expected**: Exits immediately, processing abandoned

## Future Enhancements

Potential improvements for future versions:

1. **Progress Bar**: Show processing progress during wait
2. **Job Names**: List which meetings are being processed
3. **Persistent Queue**: Save queue to disk, resume on restart
4. **Background Mode**: Detach from terminal, let processing continue
5. **Notification**: Desktop notification when processing completes

## Related Files

- [src/tui.py](../src/tui.py) - Main TUI application
- [src/processing_queue.py](../src/processing_queue.py) - Background processing queue
