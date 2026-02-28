---
name: audio_transcriber
description: **Problem Category**: Audio file transcription using OpenAI Whisper
entry_file: audio_transcriber.py
---

# audio_transcriber

## Description
**Problem Category**: Audio file transcription using OpenAI Whisper
**Applicable Questions**: Transcribing audio files (mp3, wav, etc.) to text, especially Chinese audio
**Key Features**:
- Uses OpenAI Whisper model for transcription
- Supports Chinese language transcription
- Falls back to Google Speech Recognition if Whisper fails
- Auto-installs required dependencies
- Extracts file path from natural language query via LLM
**Skills Used**: execute_shell_command
**Reasoning Pattern**: 1) Parse query for file path 2) Verify file exists 3) Install whisper 4) Transcribe with whisper (base model, zh language) 5) Fallback to SpeechRecognition if needed 6) Return transcribed text
**Input Format**: Natural language query containing an audio file path (e.g., 'Transcribe the audio file at /path/to/file.mp3')
**Output Format**: {answer: transcribed text, summary: process description}

## Skills Used
playwright, google_search, execute_shell_command

## Usage

**Entry file**: `audio_transcriber.py`

**Query type**: Pass a focused sub-question as the query.

**How to call**:
```xml
<action>run_subagent</action>
<params>{"skill_name": "audio_transcriber", "query": "<your focused sub-question>"}</params>
```
