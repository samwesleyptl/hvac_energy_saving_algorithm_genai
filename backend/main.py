import os
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.simulator import ACSimulator
from backend.agent import optimize_ac_settings
from backend.chat_agent import run_chat_agent

app = FastAPI(title="Smart AC Energy Saving Agent API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize simulator instance
simulator = ACSimulator()

# Pydantic schemas for requests
class StateUpdateSchema(BaseModel):
    target_temp: Optional[float] = None
    outdoor_temp: Optional[float] = None
    occupancy: Optional[bool] = None
    humidity: Optional[float] = None
    hour_of_day: Optional[float] = None

class OptimizeRequestSchema(BaseModel):
    api_key: Optional[str] = None
    key_type: Optional[str] = None

class ChatMessageSchema(BaseModel):
    role: str
    content: str

class ChatRequestSchema(BaseModel):
    message: str
    history: List[ChatMessageSchema] = []
    api_key: Optional[str] = None
    key_type: Optional[str] = None

@app.get("/api/state")
def get_state():
    """Retrieve the current simulator and AC status."""
    return simulator.get_state()

@app.post("/api/state")
def update_state(data: StateUpdateSchema):
    """Manually adjust simulator parameters from the client."""
    if data.target_temp is not None:
        simulator.target_temp = max(16.0, min(30.0, data.target_temp))
    if data.outdoor_temp is not None:
        simulator.outdoor_temp = max(-10.0, min(50.0, data.outdoor_temp))
    if data.occupancy is not None:
        simulator.occupancy = data.occupancy
    if data.humidity is not None:
        simulator.humidity = max(10.0, min(100.0, data.humidity))
    if data.hour_of_day is not None:
        simulator.hour_of_day = max(0.0, min(23.99, data.hour_of_day))
        
    return simulator.get_state()

@app.post("/api/step")
def run_step(
    auto_optimize: bool = True, 
    api_key: Optional[str] = Body(None, embed=True), 
    key_type: Optional[str] = Body(None, embed=True)
):
    """
    Advance the simulator environment by 5 minutes.
    If auto_optimize is True, runs the LangGraph optimizer node first and applies recommendations.
    """
    if auto_optimize:
        # Run agent optimization
        rec = optimize_ac_settings(simulator.get_state(), api_key=api_key or "", key_type=key_type or "")
        simulator.update_settings(
            power=rec["power"],
            setpoint=rec["setpoint"],
            fan_speed=rec["fan_speed"],
            mode=rec["mode"]
        )
        
    # Advance the environment thermal model
    simulator.step()
    
    # Return new state and recommendations (if optimized)
    state = simulator.get_state()
    if auto_optimize:
        state["agent_decision"] = rec
    return state

@app.post("/api/optimize")
def run_optimization(payload: Optional[OptimizeRequestSchema] = None):
    """
    Explicitly trigger the LangGraph optimization workflow based on current simulator status,
    apply recommendations to the AC, and return decision details + node execution path.
    """
    key = payload.api_key if payload else ""
    ktype = payload.key_type if payload else ""
    rec = optimize_ac_settings(simulator.get_state(), api_key=key or "", key_type=ktype or "")
    
    # Apply settings to simulator
    simulator.update_settings(
        power=rec["power"],
        setpoint=rec["setpoint"],
        fan_speed=rec["fan_speed"],
        mode=rec["mode"]
    )
    
    state = simulator.get_state()
    state["agent_decision"] = rec
    return state

@app.post("/api/chat")
def chat_with_agent(payload: ChatRequestSchema):
    """
    Interact with the AC Agent using natural language.
    Executes tool-calling actions on the simulator and returns response + tool traces.
    """
    try:
        history_dicts = [{"role": h.role, "content": h.content} for h in payload.history]
        result = run_chat_agent(
            message=payload.message,
            history=history_dicts,
            api_key=payload.api_key or "",
            key_type=payload.key_type or "",
            simulator=simulator
        )
        return {
            "response": result["response"],
            "tool_calls": result["tool_calls"],
            "simulator_state": simulator.get_state()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat Agent Error: {str(e)}")

@app.post("/api/reset")
def reset_accumulators():
    """Reset accumulated energy savings, cost savings, and CO2 reduction metrics."""
    simulator.reset_accumulators()
    return simulator.get_state()

# Serve frontend static files
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    # Fallback to prevent crash if frontend is not written yet
    @app.get("/")
    def read_root():
        return {"status": "Backend running. Please write the frontend files next."}
