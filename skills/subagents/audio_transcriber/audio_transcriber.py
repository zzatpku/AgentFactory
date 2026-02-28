import json
from tools import execute_shell_command
from llm import call_llm

def main(query):
    # Step 1: Parse the query to get the audio file path
    parse_result = call_llm(
        system="You extract file paths from user queries. Return ONLY the file path, nothing else.",
        messages=[{"role": "user", "content": f"Extract the audio file path from this query: {query}"}],
        max_tokens=500
    )
    audio_path = parse_result.strip()
    
    # Step 2: Check if the file exists
    check = execute_shell_command(f'ls -la "{audio_path}"')
    if 'No such file' in check:
        return {"answer": f"File not found: {audio_path}", "summary": f"File not found at {audio_path}. Output: {check}"}
    
    # Step 3: Check if ffmpeg is available
    ffmpeg_check = execute_shell_command('which ffmpeg')
    
    # Step 4: Try to use whisper for transcription
    # First, install openai-whisper
    install_result = execute_shell_command('pip install openai-whisper 2>&1 | tail -5')
    
    # Step 5: Try transcription with whisper
    transcribe_code = f'''
import whisper
import json

model = whisper.load_model("base")
result = model.transcribe("{audio_path}", language="en")
print(json.dumps({{"text": result["text"], "segments": [{{"start": s["start"], "end": s["end"], "text": s["text"]}} for s in result["segments"]]}}))  
'''
    
    # Write the transcription script
    execute_shell_command(f"cat > /tmp/transcribe.py << 'PYEOF'\n{transcribe_code}\nPYEOF")
    
    # Run transcription
    transcription_output = execute_shell_command('python /tmp/transcribe.py 2>&1')
    
    # If whisper fails, try alternative approach
    if 'Error' in transcription_output or 'error' in transcription_output.lower() or not transcription_output.strip():
        # Try with SpeechRecognition library
        install_sr = execute_shell_command('pip install SpeechRecognition pydub 2>&1 | tail -5')
        
        # Convert mp3 to wav first
        convert_result = execute_shell_command(f'ffmpeg -i "{audio_path}" -ar 16000 -ac 1 /tmp/audio_temp.wav -y 2>&1 | tail -5')
        
        sr_code = '''
import speech_recognition as sr
import json

recognizer = sr.Recognizer()
with sr.AudioFile("/tmp/audio_temp.wav") as source:
    audio = recognizer.record(source)
try:
    text = recognizer.recognize_google(audio, language="en-US")
    print(json.dumps({"text": text}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
'''
        execute_shell_command(f"cat > /tmp/transcribe_sr.py << 'PYEOF'\n{sr_code}\nPYEOF")
        transcription_output = execute_shell_command('python /tmp/transcribe_sr.py 2>&1')
    
    # Step 6: Parse and return the result
    try:
        result_data = json.loads(transcription_output.strip().split('\n')[-1])
        transcribed_text = result_data.get('text', '')
    except:
        transcribed_text = transcription_output
    
    # Generate summary
    summary = call_llm(
        system="You are a summarizer. Summarize the transcription process and results.",
        messages=[{"role": "user", "content": f"Query: {query}\nAudio file: {audio_path}\nFile check: {check}\nInstall result: {install_result}\nTranscription output: {transcription_output}\nFinal text: {transcribed_text}\n\nWrite a summary of the transcription process."}],
        max_tokens=1000
    )
    
    return {"answer": transcribed_text, "summary": summary}
