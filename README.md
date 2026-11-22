# Scribeling
![Status](https://img.shields.io/badge/status-work_in_progress-yellow)

A self-hosted Discord transcription and notetaking bot. It joins a voice channel and live-transcribes speech to a txt file. The transcription is then turned into structured notes.
Two stages:
- ✅ Live transcription via faster-whisper
- 🚧 Creation of structured notes via common LLM API's

In its current state the bot can make live-transcriptions that are saved to the campaign's folder, `data/campaigns/<DEFAULT_CAMPAIGN>/transcripts/`. Only one voice channel can be transcribed per discord server. The structured notes part is very much still a work in progress.

⚠️ Due to lack of alternative, the bot is currently build upon an unmerged PR of discord-ext-voice-recv due to issues with discord enforced Dave encryption.

## Setup
The bot is intended to be run as a docker container on a host machine with a Nvidia GPU + drivers.

### Docker
You'll need Docker Engine and nvidia-container-toolkit installed.

### Bot Setting
Rename the .env.example file to .env and provide any required values.

It might help to set a specific language and prompt to improve performance.

### Discord bot token
- Generate your discord bot token in the discord dev portal. 
- Set the bot to private, add bot via OAuth2 URL Generator to server.
- OAuth2 URL Generator: Check bot and applications.commands under scope and grant connect, send messages, use voice activity permissions.



## Running the finished bot (Docker)
The bot is intended to be run as a docker container. 
```bash
docker compose -f docker/docker-compose.yml up --build
```

## Commands

- `/transcribe` — Bot joins the voice channel the command giver is currently in and starts transcribing.
- `/stop` — The bot stops listening, processes remaining audio and leaves the voice channel




