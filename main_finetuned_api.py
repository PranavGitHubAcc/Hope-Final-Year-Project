import asyncio
import uuid
import os
import json
import tempfile
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from google.adk.runners import Runner
from google.genai import types

import vertexai
from vertexai import agent_engines
from google.adk.memory import VertexAiMemoryBankService
from google.adk.sessions import VertexAiSessionService
from google.adk.tools.agent_tool import AgentTool

# Import speech recognition
import speech_recognition as sr
from pydub import AudioSegment

from hope_finetuned import root_agent
from hope_finetuned.sub_agents.contacting_agent import contacting_agent


# Project configuration
load_dotenv()
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")

if not PROJECT_ID or PROJECT_ID == "[your-project-id]":
    PROJECT_ID = str(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    if not PROJECT_ID:
        raise ValueError("Project ID not found.")

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

# === PERSISTENT CONFIGURATION ===
PERSISTENCE_FILE = "agent_state.json"
APP_NAME = "hope_agent_api"

# Global variables
runner = None
memory_bank_service = None
session_service = None
agent_engine = None

class PersistentState(BaseModel):
    app_name: str
    agent_engine_id: Optional[str] = None
    created_at: str
    sessions: Dict[str, dict] = {}

def load_persistent_state() -> PersistentState:
    """Load persistent state from file or create new"""
    if Path(PERSISTENCE_FILE).exists():
        with open(PERSISTENCE_FILE, 'r') as f:
            data = json.load(f)
            return PersistentState(**data)
    else:
        return PersistentState(
            app_name=APP_NAME,
            created_at=datetime.now().isoformat(),
            sessions={}
        )

def save_persistent_state(state: PersistentState):
    """Save persistent state to file"""
    with open(PERSISTENCE_FILE, 'w') as f:
        json.dump(state.dict(), f, indent=2)

# Pydantic models
class ChatMessage(BaseModel):
    message: str = Field(..., description="The user's message")
    session_id: Optional[str] = Field(None, description="Existing session ID")
    user_id: Optional[str] = Field(None, description="User ID")

class ChatResponse(BaseModel):
    response: str
    session_id: str
    user_id: str
    transcription: Optional[str] = None

class AudioResponse(BaseModel):
    transcription: str
    response: str
    session_id: str
    user_id: str

class SessionInfo(BaseModel):
    session_id: str
    user_id: str
    created_at: str

def audio_to_text(audio_file_path: str) -> str:
    """Convert audio file to text using speech recognition"""
    try:
        recognizer = sr.Recognizer()
        
        # Convert audio file to WAV format if needed
        audio = AudioSegment.from_file(audio_file_path)
        wav_path = audio_file_path.replace(os.path.splitext(audio_file_path)[1], ".wav")
        audio.export(wav_path, format="wav")
        
        with sr.AudioFile(wav_path) as source:
            # Adjust for ambient noise and record
            recognizer.adjust_for_ambient_noise(source)
            audio_data = recognizer.record(source)
            
            # Use Google Speech Recognition
            text = recognizer.recognize_google(audio_data)
            print(f"Transcribed text: {text}")
            return text
            
    except sr.UnknownValueError:
        raise HTTPException(status_code=400, detail="Could not understand audio")
    except sr.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Speech recognition error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio processing error: {str(e)}")
    finally:
        # Clean up temporary files
        if 'wav_path' in locals() and os.path.exists(wav_path):
            os.remove(wav_path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner, memory_bank_service, session_service, agent_engine
    
    # Load persistent state
    persistent_state = load_persistent_state()
    print(f"Loaded persistent state: {persistent_state.app_name}")
    
    print(f"Initializing Agent Engine...")
    print(f"Project: {PROJECT_ID}, Location: {LOCATION}")

    vertexai_client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    # Reuse existing agent engine or create new one
    if persistent_state.agent_engine_id:
        try:
            print(f"Reusing existing Agent Engine: {persistent_state.agent_engine_id}")
            agent_engine_name = (
                f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{persistent_state.agent_engine_id}"
                if not persistent_state.agent_engine_id.startswith("projects/")
                else persistent_state.agent_engine_id
            )
            agent_engine = agent_engines.get(agent_engine_name)
        except Exception as e:
            print(f"⚠️ Could not reuse engine ({e}), creating new one...")
            agent_engine = agent_engines.create()
            persistent_state.agent_engine_id = agent_engine.name
            save_persistent_state(persistent_state)
    else:
        print("Creating new Agent Engine...")
        agent_engine = agent_engines.create()
        persistent_state.agent_engine_id = agent_engine.name
        save_persistent_state(persistent_state)

    print(f"Using Agent Engine: {agent_engine.resource_name}")

    memory_bank_service = VertexAiMemoryBankService(
        project=PROJECT_ID, 
        location=LOCATION, 
        agent_engine_id=agent_engine.name
    )

    session_service = VertexAiSessionService(
        project=PROJECT_ID, 
        location=LOCATION, 
        agent_engine_id=agent_engine.name
    )

    # Custom memory retrieval tool (now uses persistent app_name)
    async def recall_past_memories(query: str) -> str:
        print(f"[Memory Tool] Searching memories for: '{query}'")
        
        # Search across ALL users or specific user logic
        memories = await memory_bank_service.search_memory(
            app_name=persistent_state.app_name,
            user_id="default",
            query=query
        )
        
        if memories and memories.memories:
            formatted_memories = "\n".join([
                f"- {memory.content.parts[0].text}" 
                for memory in memories.memories 
                if memory.content and memory.content.parts
            ])
            print(f"Found {len(memories.memories)} relevant memories")
            return f"Relevant past conversations:\n{formatted_memories}"
        
        return "No relevant past memories found."

    # Define tools
    runner_tools = [
        recall_past_memories,
        AgentTool(contacting_agent)
    ]

    root_agent.tools = runner_tools

    # Create runner with PERSISTENT app_name
    runner = Runner(
        agent=root_agent,
        app_name=persistent_state.app_name,
        session_service=session_service,
        memory_service=memory_bank_service,
    )

    print("API initialization completed with persistent memory!")
    yield
    
    print("Shutting down API...")

app = FastAPI(
    title="Hope Agent API with Audio Processing",
    description="REST API that processes audio input and provides text responses",
    version="2.1.0",
    lifespan=lifespan
)

# Enable CORS for all origins (adjust as needed for security)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def run_single_turn(query: str, session_id: str, user_id: str) -> str:
    """Run a single conversation turn"""
    global runner
    
    if not runner:
        raise HTTPException(status_code=503, detail="Agent runner not initialized")
    
    content = types.Content(role="user", parts=[types.Part(text=query)])
    events = runner.run(user_id=user_id, session_id=session_id, new_message=content)

    for event in events:
        if event.is_final_response():
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    return part.text
    
    return "Assistant: (No readable text response)"

async def create_new_session(user_id: str) -> str:
    """Create a new session and persist it"""
    global session_service
    persistent_state = load_persistent_state()
    
    session = await session_service.create_session(
        app_name=persistent_state.app_name,
        user_id=user_id,
    )
    
    # Persist session info
    persistent_state.sessions[session.id] = {
        "user_id": user_id,
        "created_at": datetime.now().isoformat()
    }
    save_persistent_state(persistent_state)
    
    return session.id

@app.post("/chat", response_model=ChatResponse)
async def chat(chat_message: ChatMessage, background_tasks: BackgroundTasks):
    """Send a message to the agent with memory recall"""
    global runner
    
    if not runner:
        raise HTTPException(status_code=503, detail="Agent runner not initialized")
    
    persistent_state = load_persistent_state()
    user_id = chat_message.user_id or f"user_{uuid.uuid4()}"
    
    # Create new session or use existing one
    if chat_message.session_id:
        session_id = chat_message.session_id
        if session_id not in persistent_state.sessions:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session_id = await create_new_session(user_id)
    
    try:
        response_text = await run_single_turn(
            query=chat_message.message,
            session_id=session_id,
            user_id=user_id
        )
        
        return ChatResponse(
            response=response_text,
            session_id=session_id,
            user_id=user_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")

@app.post("/process_audio", response_model=AudioResponse)
async def process_audio(
    file: UploadFile = File(...),
    user_id: str = Form("user_unknown"),
    session_id: Optional[str] = Form(None)
):
    """Process audio file: convert to text and get agent response"""
    global runner
    
    if not runner:
        raise HTTPException(status_code=503, detail="Agent runner not initialized")
    
    # Validate file type
    if not file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="File must be an audio file")
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
        temp_path = temp_file.name
        content = await file.read()
        temp_file.write(content)
    
    try:
        # Convert audio to text
        transcription = audio_to_text(temp_path)
        
        persistent_state = load_persistent_state()
        
        # Create new session or use existing one
        if not session_id:
            session_id = await create_new_session(user_id)
        else:
            if session_id not in persistent_state.sessions:
                session_id = await create_new_session(user_id)
        
        # Get agent response
        response_text = await run_single_turn(
            query=transcription,
            session_id=session_id,
            user_id=user_id
        )
        
        return AudioResponse(
            transcription=transcription,
            response=response_text,
            session_id=session_id,
            user_id=user_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")
    finally:
        # Clean up temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.get("/memory/search")
async def search_memory(query: str, user_id: str = "default"):
    """Directly search memory bank"""
    global memory_bank_service
    persistent_state = load_persistent_state()
    
    memories = await memory_bank_service.search_memory(
        app_name=persistent_state.app_name,
        user_id=user_id,
        query=query
    )
    
    if memories and memories.memories:
        return {
            "query": query,
            "found_memories": len(memories.memories),
            "memories": [
                memory.content.parts[0].text 
                for memory in memories.memories 
                if memory.content and memory.content.parts
            ]
        }
    return {"query": query, "found_memories": 0, "memories": []}

@app.post("/sessions/new", response_model=ChatResponse)
async def create_session(user_id: Optional[str] = None):
    """Create a new chat session"""
    user_id = user_id or f"user_{uuid.uuid4()}"
    session_id = await create_new_session(user_id)
    
    return ChatResponse(
        response="New session created. I can remember our past conversations!",
        session_id=session_id,
        user_id=user_id
    )

@app.get("/sessions")
async def list_sessions():
    """List all persisted sessions"""
    persistent_state = load_persistent_state()
    return persistent_state.sessions

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)