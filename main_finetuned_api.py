import asyncio
import uuid
import os
import json
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from google.adk.runners import Runner
from google.genai import types

import vertexai
from vertexai import agent_engines
from google.adk.memory import VertexAiMemoryBankService
from google.adk.sessions import VertexAiSessionService
from google.adk.tools.agent_tool import AgentTool

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
APP_NAME = "hope_agent_api"  # ← FIXED app name for memory persistence

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

class SessionInfo(BaseModel):
    session_id: str
    user_id: str
    created_at: str

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
            app_name=persistent_state.app_name,  # ← PERSISTENT app name!
            user_id="default",  # You might want to make this dynamic
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
        app_name=persistent_state.app_name,  # ← Same name every time!
        session_service=session_service,
        memory_service=memory_bank_service,
    )

    print("API initialization completed with persistent memory!")
    yield
    
    # Shutdown - don't delete engine if we want to persist!
    print("Shutting down API...")
    # Comment out engine deletion to preserve memory
    # agent_engines.delete(resource_name=agent_engine.resource_name, force=True)

app = FastAPI(
    title="Hope Agent API with Persistent Memory",
    description="REST API that remembers conversations across restarts",
    version="2.0.0",
    lifespan=lifespan
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