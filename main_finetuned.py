import asyncio
import uuid
import os
import json
import logging
import io
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import speech_recognition as sr
from pydub import AudioSegment

from google.adk.runners import Runner
from google.genai import types
import vertexai
from vertexai import agent_engines
from google.adk.memory import VertexAiMemoryBankService
from google.adk.sessions import VertexAiSessionService
from google.adk.tools.agent_tool import AgentTool

# Import your agents
from hope_finetuned import root_agent
from hope_finetuned.sub_agents.contacting_agent import contacting_agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================================
# Configuration
# ==========================================================
load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
AGENT_ENGINE_ID = os.getenv("AGENT_ENGINE_ID")
USER_ID = os.getenv("USER_ID")

USER_ID_FILE = "user_id.json"

# Safety checks
if not PROJECT_ID:
    raise ValueError("❌ PROJECT_ID missing in .env")
if not AGENT_ENGINE_ID:
    raise ValueError("❌ AGENT_ENGINE_ID missing in .env")

# Vertex setup
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

# Flask app
app = Flask(__name__)
CORS(app)

# Global variables
runner = None
app_name = "hope_agent_app"
memory_bank_service = None
session_service = None
active_sessions = {}  # Track active sessions

# ==========================================================
# Helper Functions
# ==========================================================

def get_or_create_user_id():
    """Persist user ID between runs."""
    global USER_ID
    if USER_ID:
        logger.info(f"🧑‍💻 Using USER_ID from .env: {USER_ID}")
        return USER_ID
    if os.path.exists(USER_ID_FILE):
        with open(USER_ID_FILE, "r") as f:
            data = json.load(f)
            USER_ID = data.get("USER_ID")
            logger.info(f"🧑‍💻 Loaded USER_ID from file: {USER_ID}")
            return USER_ID
    new_id = f"user_{uuid.uuid4()}"
    with open(USER_ID_FILE, "w") as f:
        json.dump({"USER_ID": new_id}, f)
    logger.info(f"🆕 Created new USER_ID: {new_id}")
    return new_id


def ensure_wav_format(audio_data: bytes, content_type: str = None) -> bytes:
    """Ensure audio data is in WAV format."""
    try:
        if content_type and 'wav' in content_type.lower():
            audio = AudioSegment.from_wav(io.BytesIO(audio_data))
        else:
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data))
            except Exception as e:
                logger.error(f"Could not parse audio file: {str(e)}")
                raise Exception("Invalid audio file format")
        
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
        wav_data = ensure_wav_format(audio_data)
        
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        recognizer.phrase_threshold = 0.3
        
        with sr.AudioFile(io.BytesIO(wav_data)) as source:
            audio = recognizer.record(source)
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


async def recall_past_memories(query: str) -> str:
    """Memory recall tool for the agent."""
    logger.info(f"🧠 [Tool] recall_past_memories called with: '{query}'")
    memories = await memory_bank_service.search_memory(
        app_name=app_name, user_id=USER_ID, query=query
    )
    if memories and memories.memories:
        formatted = "\n".join(
            [f"- {m.content.parts[0].text}" for m in memories.memories if m.content and m.content.parts]
        )
        return f"Here are some relevant past memories:\n{formatted}"
    return "No relevant past memories found."


async def run_agent_query(query: str, user_id: str, session_id: str) -> str:
    """Send query to agent and get response."""
    content = types.Content(role="user", parts=[types.Part(text=query)])
    events = runner.run(user_id=user_id, session_id=session_id, new_message=content)

    response_text = None
    for event in events:
        if event.is_final_response():
            logger.info("--- Final Response Received ---")
            for i, part in enumerate(event.content.parts):
                if hasattr(part, "text") and part.text:
                    logger.info(f"Assistant (Part {i}): {part.text}")
            if event.content.parts and hasattr(event.content.parts[0], "text"):
                response_text = event.content.parts[0].text
            else:
                response_text = "(No readable response)"
    
    return response_text or "No response available"


async def initialize_agent_system():
    """Initialize the agent system on startup."""
    global runner, memory_bank_service, session_service, USER_ID
    
    logger.info(f"✅ Project: {PROJECT_ID}")
    logger.info(f"🌍 Location: {LOCATION}")
    
    USER_ID = get_or_create_user_id()
    logger.info(f"🧑‍💻 User ID: {USER_ID}")

    _ = vertexai.Client(project=PROJECT_ID, location=LOCATION)

    logger.info(f"🔁 Loading existing Agent Engine: {AGENT_ENGINE_ID}")
    agent_engine = agent_engines.get(resource_name=AGENT_ENGINE_ID)
    logger.info(f"Using Agent Engine: {agent_engine.resource_name}")

    memory_bank_service = VertexAiMemoryBankService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine.name
    )
    session_service = VertexAiSessionService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine.name
    )

    runner_tools = [recall_past_memories, AgentTool(contacting_agent)]
    root_agent.tools = runner_tools

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        memory_service=memory_bank_service,
    )
    
    logger.info("✅ Agent system initialized successfully")


async def create_agent_session(user_id: str, session_id: str):
    """Create a new session for the agent."""
    try:
        session = await runner.session_service.create_session(
            app_name=app_name, 
            user_id=user_id
        )
        active_sessions[f"{user_id}:{session_id}"] = session.id
        logger.info(f"Created new agent session: {session.id}")
        return session.id
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise


async def ensure_session_exists(user_id: str, session_id: str) -> str:
    """Ensure a session exists, create if it doesn't."""
    session_key = f"{user_id}:{session_id}"
    
    if session_key in active_sessions:
        logger.info(f"Session {session_id} already exists for user {user_id}")
        return active_sessions[session_key]
    
    agent_session_id = await create_agent_session(user_id, session_id)
    return agent_session_id


async def save_session_to_memory(user_id: str, agent_session_id: str):
    """Save session to memory."""
    try:
        logger.info("💾 Saving session to memory...")
        completed_session = await runner.session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=agent_session_id
        )
        await memory_bank_service.add_session_to_memory(completed_session)
        logger.info("✅ Session saved successfully.")
    except Exception as e:
        logger.error(f"Error saving session to memory: {str(e)}")


# ==========================================================
# API Routes
# ==========================================================

@app.route('/api/create_session', methods=['POST'])
def create_session_endpoint():
    """Create a new session."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        user_id = data.get('user_id', USER_ID)
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({"error": "Missing session_id"}), 400
        
        logger.info(f"Creating session - user_id: {user_id}, session_id: {session_id}")
        
        # Run async function in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        agent_session_id = loop.run_until_complete(ensure_session_exists(user_id, session_id))
        loop.close()
        
        return jsonify({
            "status": "success",
            "message": "Session created successfully",
            "user_id": user_id,
            "session_id": session_id,
            "agent_session_id": agent_session_id
        })
        
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/process_audio', methods=['POST'])
def process_audio():
    """Process an audio file: convert speech to text and send to agent."""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        
        file = request.files['file']
        user_id = request.form.get('user_id', USER_ID)
        session_id = request.form.get('session_id')
        
        if not session_id:
            return jsonify({"error": "Missing session_id"}), 400
        
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
        
        # Ensure session exists and process query
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        agent_session_id = loop.run_until_complete(ensure_session_exists(user_id, session_id))
        response = loop.run_until_complete(run_agent_query(text, user_id, agent_session_id))
        
        loop.close()
        
        response_data = {
            "status": "success",
            "transcription": text,
            "response": response
        }
        
        logger.info(f"Returning response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/end_session', methods=['POST'])
def end_session():
    """End a session and save to memory."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        user_id = data.get('user_id', USER_ID)
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({"error": "Missing session_id"}), 400
        
        session_key = f"{user_id}:{session_id}"
        
        if session_key not in active_sessions:
            return jsonify({"error": "Session not found"}), 404
        
        agent_session_id = active_sessions[session_key]
        
        # Save session to memory
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(save_session_to_memory(user_id, agent_session_id))
        loop.close()
        
        # Remove from active sessions
        del active_sessions[session_key]
        
        return jsonify({
            "status": "success",
            "message": "Session ended and saved to memory"
        })
        
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "message": "Agent audio processing service is running",
        "active_sessions": len(active_sessions),
        "agent_initialized": runner is not None
    })


@app.route('/', methods=['GET'])
def root():
    """Root endpoint."""
    return jsonify({
        "message": "Agent Audio Processing API",
        "version": "1.0.0",
        "endpoints": {
            "create_session": "/api/create_session (POST)",
            "process_audio": "/api/process_audio (POST)",
            "end_session": "/api/end_session (POST)",
            "health": "/health (GET)"
        }
    })


# ==========================================================
# Startup
# ==========================================================

if __name__ == "__main__":
    logger.info("Starting Agent Audio Processing Service...")
    logger.info(f"Project: {PROJECT_ID}")
    logger.info(f"Location: {LOCATION}")
    logger.info(f"Agent Engine ID: {AGENT_ENGINE_ID}")
    
    # Initialize agent system before starting Flask
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_agent_system())
    loop.close()
    
    logger.info("🚀 Starting Flask server...")
    
    app.run(
        host="0.0.0.0",
        port=3000,
        debug=False  # Set to False to avoid issues with async
    )