# Meeting Recorder Processing Server

FastAPI server for GPU-accelerated transcription and summarization.

## Features

- **GPU-Accelerated Transcription**: Uses faster-whisper with CUDA support
- **Automatic Summarization**: Integrates with Ollama for meeting summaries
- **Health Monitoring**: `/health` endpoint for availability checks
- **Simple REST API**: Single `/api/process` endpoint for processing recordings

## Installation

### 1. Install Dependencies

```bash
cd server
pip install -r requirements.txt
```

### 2. GPU Support (Optional but Recommended)

**For NVIDIA GPUs:**
```bash
# Install PyTorch with CUDA support
pip install torch torchvision torchaudio

# Verify CUDA is available
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

**For CPU-only:**
No additional packages needed. Will use int8 quantization for faster CPU inference.

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

**Key Configuration Options:**

```bash
# GPU Configuration (Recommended for firecorn.net with RTX 2000 ADA)
WHISPER_MODEL=base  # or medium for better quality
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# Ollama Configuration
OLLAMA_ENDPOINT=https://ollama.firecorn.net

# Server Configuration
HOST=0.0.0.0
PORT=8000
```

## Running the Server

### Development Mode

```bash
python main.py
```

Server will start on `http://0.0.0.0:8000`

### Production Mode with systemd

Create `/etc/systemd/system/meeting-recorder-server.service`:

```ini
[Unit]
Description=Meeting Recorder Processing Server
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/Meeting-Notes/server
Environment="PATH=/path/to/venv/bin"
EnvironmentFile=/path/to/Meeting-Notes/server/.env
ExecStart=/path/to/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable meeting-recorder-server
sudo systemctl start meeting-recorder-server
sudo systemctl status meeting-recorder-server
```

### Production Mode with Docker (Alternative)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# For GPU support, use nvidia/cuda base image instead
# FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# Copy server code
COPY main.py .

# Expose port
EXPOSE 8000

# Run server
CMD ["python", "main.py"]
```

Build and run:
```bash
docker build -t meeting-recorder-server .
docker run -p 8000:8000 --env-file .env meeting-recorder-server

# For GPU support:
docker run --gpus all -p 8000:8000 --env-file .env meeting-recorder-server
```

## API Endpoints

### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "model": "base"
}
```

### Process Recording

```bash
POST /api/process
Content-Type: multipart/form-data

Fields:
- audio: WAV audio file
- title: Meeting title
- whisper_model: (optional) Override Whisper model
- ollama_model: LLM model for summarization (default: qwen3:8b-q8_0)
```

**Response:**
```json
{
  "success": true,
  "transcript": "# Meeting Transcript...",
  "summary": "Summary text...",
  "processing_time": 45.2,
  "transcription_time": 30.1,
  "summarization_time": 15.1
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:8000/api/process \
  -F "audio=@recording.wav" \
  -F "title=Team Standup" \
  -F "ollama_model=qwen3:8b-q8_0"
```

## Deployment to firecorn.net

### Prerequisites

- Server with NVIDIA GPU (RTX 2000 ADA)
- CUDA drivers installed
- Ollama running on https://ollama.firecorn.net
- SSL certificate for HTTPS

### Setup Steps

1. **Install CUDA drivers:**
   ```bash
   # Check NVIDIA GPU
   nvidia-smi

   # Install CUDA toolkit (if not installed)
   # See: https://developer.nvidia.com/cuda-downloads
   ```

2. **Clone repository:**
   ```bash
   cd /opt
   git clone https://github.com/your-username/Meeting-Notes.git
   cd Meeting-Notes/server
   ```

3. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install torch torchvision torchaudio  # For GPU support
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   nano .env
   # Set WHISPER_DEVICE=cuda, etc.
   ```

5. **Test server:**
   ```bash
   python main.py
   # Verify GPU is detected in startup logs
   ```

6. **Set up systemd service** (see Production Mode section above)

7. **Configure reverse proxy** (nginx for HTTPS):
   ```nginx
   server {
       listen 8000 ssl http2;
       server_name firecorn.net;

       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_read_timeout 600s;  # 10 min for long recordings
       }
   }
   ```

8. **Start service:**
   ```bash
   sudo systemctl start meeting-recorder-server
   ```

9. **Test from client:**
   ```bash
   # Update client config.yaml:
   # processing:
   #   mode: hybrid
   #   server:
   #     url: https://firecorn.net:8000

   # Record a meeting and watch processing logs
   ```

## Performance

### NVIDIA RTX 2000 ADA (12GB)

Expected processing times for 30-minute meeting:

| Model | Transcription | Summarization | Total |
|-------|--------------|---------------|-------|
| tiny  | ~30s | ~10s | ~40s |
| base  | ~1min | ~10s | ~1.5min |
| small | ~1.5min | ~10s | ~2min |
| medium | ~2.5min | ~10s | ~3min |

### CPU-Only Server

| Model | Transcription | Total |
|-------|--------------|-------|
| tiny  | ~2min | ~2.5min |
| base  | ~3-4min | ~4-5min |

## Monitoring

### View Logs

```bash
# systemd service
sudo journalctl -u meeting-recorder-server -f

# Docker
docker logs -f meeting-recorder-server
```

### Check Health

```bash
curl https://firecorn.net:8000/health
```

### Monitor GPU Usage

```bash
# Watch GPU utilization during processing
watch -n 1 nvidia-smi
```

## Troubleshooting

### GPU Not Detected

```bash
# Verify CUDA installation
python -c "import torch; print(torch.cuda.is_available())"

# Check NVIDIA drivers
nvidia-smi

# Verify environment
cat .env | grep WHISPER_DEVICE
```

### Port Already in Use

```bash
# Check what's using port 8000
sudo lsof -i :8000

# Change port in .env
echo "PORT=8001" >> .env
```

### Out of Memory

- Reduce `WHISPER_MODEL` to smaller size (base → tiny)
- Process one recording at a time
- Restart service to clear GPU memory: `sudo systemctl restart meeting-recorder-server`

### Ollama Connection Failed

```bash
# Test Ollama endpoint
curl https://ollama.firecorn.net/api/tags

# Update .env if needed
echo "OLLAMA_ENDPOINT=https://ollama.firecorn.net" >> .env
```

## Security

### API Key Authentication (Optional)

To add API key authentication, modify `main.py`:

```python
from fastapi import Header, HTTPException

API_KEY = os.getenv("API_KEY", "")

async def verify_api_key(x_api_key: str = Header(...)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.post("/api/process", dependencies=[Depends(verify_api_key)])
async def process_recording(...):
    # ...
```

Then set in `.env`:
```bash
API_KEY=your-secret-key-here
```

And update client `config.yaml`:
```yaml
processing:
  server:
    api_key: your-secret-key-here
```

## License

Same as main project.
