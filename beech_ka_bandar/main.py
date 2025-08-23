import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import speech_recognition as sr
from pydub import AudioSegment
import io
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
ADK_API_URL = os.getenv("ADK_API_URL", "http://localhost:8000/run")

def ensure_wav_format(audio_data: bytes, content_type: str = None) -> bytes:
    """Ensure audio data is in WAV format."""
    try:
        # Create AudioSegment from the input data
        if content_type and 'wav' in content_type.lower():
            audio = AudioSegment.from_wav(io.BytesIO(audio_data))
        else:
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data))
            except Exception as e:
                logger.error(f"Could not parse audio file: {str(e)}")
                return jsonify({"error": "Invalid audio file format"}), 400
        
        # Ensure it's in a standard WAV format (16-bit PCM, 16kHz for speech recognition)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        
        # Export to WAV format
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_data = wav_io.getvalue()
        
        logger.info(f"Audio converted to WAV: {len(wav_data)} bytes, duration: {len(audio)}ms")
        return wav_data
        
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        raise Exception(f"Error processing audio file: {str(e)}")

def speech_to_text(audio_data: bytes) -> str:
    """Convert speech audio to text using Google's speech recognition."""
    try:
        # Ensure audio is in WAV format
        wav_data = ensure_wav_format(audio_data)
        
        # Use speech recognition
        recognizer = sr.Recognizer()
        
        # Adjust recognizer settings for better accuracy
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        recognizer.phrase_threshold = 0.3
        
        # Create AudioFile from WAV data
        with sr.AudioFile(io.BytesIO(wav_data)) as source:
            # Record the audio data
            audio = recognizer.record(source)
            
            # Recognize speech using Google Speech Recognition
            text = recognizer.recognize_google(audio)
            logger.info(f"Successfully transcribed: '{text}'")
            return text
            
    except sr.UnknownValueError:
        logger.warning("Could not understand audio")
        raise Exception("Could not understand the audio. Please speak clearly and try again.")
    except sr.RequestError as e:
        logger.error(f"Speech recognition service error: {str(e)}")
        raise Exception("Speech recognition service is unavailable")
    except Exception as e:
        logger.error(f"Error in speech to text: {str(e)}")
        raise Exception(f"Error processing speech: {str(e)}")

def send_to_adk(user_id: str, session_id: str, text: str) -> dict:
    """Send the transcribed text to the ADK service."""
    try:
        payload = {
            "app_name": "hope_updated",
            "user_id": user_id,
            "session_id": session_id,
            "new_message": {
                "parts": [{"text": text}],
                "role": "user"
            },
            "streaming": False,
            "state_delta": {}
        }
        
        logger.info(f"Sending to ADK: {text}")
        logger.info(f"Using ADK_API_URL: {ADK_API_URL}")
        
        response = requests.post(
            ADK_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        logger.info(f"ADK Response Status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"ADK Error: {response.status_code} - {response.text}")
            raise Exception(f"ADK service error: {response.status_code}")
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"ADK Request Error: {str(e)}")
        raise Exception(f"Cannot connect to ADK service: {str(e)}")

@app.route('/api/process_audio', methods=['POST'])
def process_audio():
    """Process an audio file: convert speech to text and send to ADK service."""
    try:
        # Get form data
        if 'file' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        
        file = request.files['file']
        user_id = request.form.get('user_id')
        session_id = request.form.get('session_id')
        
        if not user_id or not session_id:
            return jsonify({"error": "Missing user_id or session_id"}), 400
        
        logger.info(f"Received audio processing request - user_id: {user_id}, session_id: {session_id}")
        logger.info(f"File info - filename: {file.filename}, content_type: {file.content_type}")
        
        # Validate file
        if not file.content_type or not file.content_type.startswith('audio/'):
            return jsonify({"error": "File must be an audio file"}), 400
        
        # Read the audio file
        audio_data = file.read()
        logger.info(f"Read {len(audio_data)} bytes of audio data")
        
        if len(audio_data) == 0:
            return jsonify({"error": "Empty audio file"}), 400
        
        # Convert speech to text
        logger.info("Starting speech-to-text conversion...")
        text = speech_to_text(audio_data)
        logger.info(f"Transcribed text: '{text}'")
        
        # Send to ADK service
        logger.info("Sending to ADK service...")
        adk_response = send_to_adk(user_id, session_id, text)
        
        # Extract the final response from ADK
        final_response = "No response available"
        if isinstance(adk_response, list) and len(adk_response) > 0:
            # Look for final_response in stateDelta
            for item in adk_response:
                if isinstance(item, dict) and "actions" in item:
                    state_delta = item.get("actions", {}).get("stateDelta", {})
                    if "final_response" in state_delta:
                        final_response = state_delta["final_response"]
                        break
            
            # If no final_response found, get text from last item
            if final_response == "No response available":
                last_item = adk_response[-1]
                if isinstance(last_item, dict) and "content" in last_item:
                    parts = last_item.get("content", {}).get("parts", [])
                    if parts and len(parts) > 0:
                        final_response = parts[0].get("text", "No response available")
        
        response_data = {
            "status": "success",
            "transcription": text,
            "response": final_response
        }
        
        logger.info(f"Returning response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok", "message": "Audio processing service is running"})

@app.route('/', methods=['GET'])
def root():
    """Root endpoint."""
    return jsonify({"message": "Audio Processing Middleware API", "version": "1.0.0"})

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=3000,
        debug=True
    )