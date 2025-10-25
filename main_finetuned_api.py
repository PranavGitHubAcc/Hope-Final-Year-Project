import asyncio
import uuid
import os
from dotenv import load_dotenv
from typing import Dict, List, Optional

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

# Import root_agent and your sub-agent instances from hope_v3
from hope_finetuned import root_agent
from hope_finetuned.sub_agents.contacting_agent import contacting_agent

# Project configuration
load_dotenv()
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")

if not PROJECT_ID or PROJECT_ID == "[your-project-id]":
    PROJECT_ID = str(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    if not PROJECT_ID:
        raise ValueError("Project ID not found. Please set it in your .env file as 'PROJECT_ID' or as the GOOGLE_CLOUD_PROJECT environment variable.")

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

# Persistent configuration for sessions and memories

# Global variables to store API state
runner = None
memory_bank_service = None
session_service = None
agent_engine = None
app_name = None

# Pydantic models for request/response
class ChatMessage(BaseModel):
    message: str = Field(..., description="The user's message")
    session_id: Optional[str] = Field(None, description="Existing session ID. If not provided, a new session will be created")
    user_id: Optional[str] = Field(None, description="User ID. If not provided, a random one will be generated")

class ChatResponse(BaseModel):
    response: str = Field(..., description="The assistant's response")
    session_id: str = Field(..., description="Session ID for continuing conversation")
    user_id: str = Field(..., description="User ID for this conversation")

class SessionInfo(BaseModel):
    session_id: str
    user_id: str
    created_at: str

class HealthCheck(BaseModel):
    status: str
    project_id: str
    location: str
    agent_engine: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize agent engine and services
    global runner, memory_bank_service, session_service, agent_engine, app_name
    
    print(f"Initializing Agent Engine...")
    print(f"Project: {PROJECT_ID}")
    print(f"Location: {LOCATION}")

    vertexai_client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    print("Creating Agent Engine...")
    agent_engine = agent_engines.create()
    print(f"Created Agent Engine: {agent_engine.resource_name}")

    app_name = "my_agent_api_" + str(uuid.uuid4())[:8]
    agent_engine_id = agent_engine.name

    memory_bank_service = VertexAiMemoryBankService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine_id
    )

    session_service = VertexAiSessionService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine_id
    )

    # Custom memory retrieval tool
    async def recall_past_memories(query: str) -> str:
        print(f"[Tool Call] Calling 'recall_past_memories' with query: '{query}'")
        memories = await memory_bank_service.search_memory(
            app_name=app_name, 
            user_id="default_user",  # Using default for tool calls
            query=query
        )
        if memories:
            formatted_memories = "\n".join([
                f"- {m.content.parts[0].text}" 
                for m in memories.memories 
                if m.content and m.content.parts
            ])
            if formatted_memories:
                print("Formatted Memories:\n", formatted_memories)
                return f"The user in previous conversations had mentioned:\n{formatted_memories}"
        return "No relevant past memories found."

    # Define tools for the Runner
    runner_tools = [
        recall_past_memories,
        AgentTool(contacting_agent)
    ]

    # Assign tools to root agent
    root_agent.tools = runner_tools

    # Create runner
    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        memory_service=memory_bank_service,
    )

    print("API initialization completed successfully!")
    yield
    
    # Shutdown: Cleanup resources
    print("Shutting down API...")
    if agent_engine:
        print(f"Deleting AgentEngine resource: {agent_engine.resource_name}")
        try:
            agent_engines.delete(resource_name=agent_engine.resource_name, force=True)
            print(f"AgentEngine resource deleted: {agent_engine.resource_name}")
        except Exception as e:
            print(f"Error deleting AgentEngine: {e}")

# Create FastAPI app with lifespan
app = FastAPI(
    title="Hope Agent API",
    description="REST API for Hope AI Agent with memory capabilities",
    version="1.0.0",
    lifespan=lifespan
)

# Store active sessions (in production, use a proper database)
active_sessions: Dict[str, SessionInfo] = {}

async def run_single_turn(query: str, session_id: str, user_id: str) -> str:
    """Run a single conversation turn and return the response."""
    global runner
    
    if not runner:
        raise HTTPException(status_code=503, detail="Agent runner not initialized")
    
    content = types.Content(role="user", parts=[types.Part(text=query)])
    events = runner.run(user_id=user_id, session_id=session_id, new_message=content)

    response_content = None
    for event in events:
        if event.is_final_response():
            print(f"\n--- Final response received for session {session_id} ---")
            for i, part in enumerate(event.content.parts):
                print(f"  Part {i}: type={type(part)}")
                if hasattr(part, 'text') and part.text:
                    print(f"    Text (first 100 chars): {part.text[:100]}...")
                    response_content = part.text
                if hasattr(part, 'function_call') and part.function_call:
                    print(f"    Function Call Name: {part.function_call.name}")
                    print(f"    Function Call Args: {part.function_call.args}")
                if hasattr(part, 'function_response') and part.function_response:
                    print(f"    Function Response Name: {part.function_response.name}")
                    print(f"    Function Response Content: {part.function_response.response}")

    return response_content or "Assistant: (No readable text response)"

async def create_new_session(user_id: str) -> str:
    """Create a new session and return session ID."""
    global session_service, app_name
    
    session = await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
    )
    
    # Store session info
    active_sessions[session.id] = SessionInfo(
        session_id=session.id,
        user_id=user_id,
        created_at=str(uuid.uuid4())  # In production, use actual timestamp
    )
    
    return session.id

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Hope Agent API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "sessions": "/sessions",
            "new_session": "/sessions/new"
        }
    }

@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint."""
    global agent_engine, PROJECT_ID, LOCATION
    
    if not agent_engine:
        raise HTTPException(status_code=503, detail="Agent engine not initialized")
    
    return HealthCheck(
        status="healthy",
        project_id=PROJECT_ID,
        location=LOCATION,
        agent_engine=agent_engine.resource_name
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(chat_message: ChatMessage, background_tasks: BackgroundTasks):
    """Send a message to the agent and get a response."""
    global runner, memory_bank_service, app_name
    
    if not runner:
        raise HTTPException(status_code=503, detail="Agent runner not initialized")
    
    # Generate or use provided user_id
    user_id = chat_message.user_id or f"user_{uuid.uuid4()}"
    
    # Create new session or use existing one
    if chat_message.session_id:
        session_id = chat_message.session_id
        # Verify session exists
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session_id = await create_new_session(user_id)
    
    # Process the message
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

@app.post("/sessions/new", response_model=ChatResponse)
async def create_session(user_id: Optional[str] = None):
    """Create a new chat session."""
    user_id = user_id or f"user_{uuid.uuid4()}"
    session_id = await create_new_session(user_id)
    
    return ChatResponse(
        response="New session created. How can I help you today?",
        session_id=session_id,
        user_id=user_id
    )

@app.get("/sessions", response_model=List[SessionInfo])
async def list_sessions():
    """List all active sessions."""
    return list(active_sessions.values())

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, background_tasks: BackgroundTasks):
    """Delete a session and add it to memory bank."""
    global memory_bank_service, session_service, app_name
    
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    user_id = active_sessions[session_id].user_id
    
    try:
        # Get completed session
        completed_session = await session_service.get_session(
            app_name=app_name, 
            user_id=user_id, 
            session_id=session_id
        )
        
        # Add to memory bank
        await memory_bank_service.add_session_to_memory(completed_session)
        print(f"Session {session_id} added to memory bank.")
        
        # Remove from active sessions
        del active_sessions[session_id]
        
        return {"message": f"Session {session_id} deleted and added to memory"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)