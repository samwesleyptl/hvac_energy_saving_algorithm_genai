import os
import json
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from backend.rag import get_policy_retriever

# Define State Structure
class AgentState(TypedDict):
    # Inputs from simulator
    indoor_temp: float
    outdoor_temp: float
    target_temp: float
    occupancy: bool
    humidity: float
    is_peak_hours: bool
    electricity_rate: float
    time_of_day: str
    
    # Internal variables
    api_key: Optional[str]
    key_type: Optional[str]
    retrieved_policies: List[str]
    
    # Outputs recommended by Agent
    recommended_power: str         # "ON" or "OFF"
    recommended_setpoint: float
    recommended_fan_speed: str     # "Low", "Medium", "High"
    recommended_mode: str          # "Cool", "Eco", "Dry", "Fan"
    estimated_savings_pct: float
    explanation: str
    
    # Graph tracking
    nodes_executed: List[str]

# Node 1: Retrieve relevant policies from LangChain RAG
def retrieve_policies_node(state: AgentState) -> Dict[str, Any]:
    nodes = list(state.get("nodes_executed", []))
    nodes.append("retrieve_policies")
    
    # Formulate query based on environmental status
    conditions = []
    if not state["occupancy"]:
        conditions.append("unoccupied")
    if state["is_peak_hours"]:
        conditions.append("peak hours tariff")
    if state["humidity"] > 60:
        conditions.append("high humidity")
    if state["outdoor_temp"] < 24.0:
        conditions.append("moderate cool outdoor")
    
    # Add time of day clues
    hour = int(state["time_of_day"].split(":")[0])
    if hour >= 22 or hour <= 6:
        conditions.append("sleep night hours")
        
    query = " ".join(conditions) if conditions else "standard comfort cooling"
    
    # Run retriever
    retriever = get_policy_retriever(api_key=state.get("api_key", ""))
    docs = retriever.invoke(query)
    
    policy_texts = [doc.page_content for doc in docs]
    
    return {
        "retrieved_policies": policy_texts,
        "nodes_executed": nodes
    }

# Node 2: Optimize settings based on policies and state
def optimize_settings_node(state: AgentState) -> Dict[str, Any]:
    nodes = list(state.get("nodes_executed", []))
    nodes.append("optimize_settings")
    
    api_key = state.get("api_key") or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    key_type = state.get("key_type")
    if api_key and not key_type:
        key_type = "gemini" if api_key.startswith("AIzaSy") else "openai"
    
    fallback_explanation = ""
    
    if api_key:
        if key_type == "gemini":
            try:
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                
                system_instruction = """You are an intelligent HVAC Energy Optimizer. Your goal is to maximize energy savings while maintaining reasonable user comfort.
You will receive the current room parameters and a set of retrieved policy guidelines.
Analyze the policies and environmental conditions to output the optimal AC settings.

You MUST return your output in JSON format with EXACTLY the following structure:
{
  "power": "ON" or "OFF",
  "setpoint": float (thermostat setting in °C, must be between 18.0 and 30.0),
  "fan_speed": "Low", "Medium", or "High",
  "mode": "Cool", "Eco", "Dry", or "Fan",
  "estimated_savings_pct": float (from 0 to 100, estimate the savings this optimization achieves relative to running normal cooling),
  "explanation": "A concise step-by-step description of why these settings were selected, referencing the applicable policies."
}"""

                policies_text = "\n".join([f"- {p}" for p in state["retrieved_policies"]])
                user_prompt = f"""### Environmental parameters:
- Indoor Temperature: {state["indoor_temp"]}°C
- Outdoor Temperature: {state["outdoor_temp"]}°C
- Target Comfort Temperature: {state["target_temp"]}°C
- Occupancy: {"Yes" if state["occupancy"] else "No"} (Is someone in the room?)
- Humidity: {state["humidity"]}%
- Peak tariff hour: {"Yes" if state["is_peak_hours"] else "No"} (Electricity rate is {state["electricity_rate"]} USD/kWh)
- Time of Day: {state["time_of_day"]}

### Retrieved Policies:
{policies_text}

Provide the optimized AC settings in JSON format:"""

                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": f"{system_instruction}\n\n{user_prompt}"}]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.0,
                        "responseMimeType": "application/json"
                    }
                }
                
                response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
                response.raise_for_status()
                res_json = response.json()
                
                text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                res = json.loads(text_content.strip())
                
                return {
                    "recommended_power": res.get("power", "ON"),
                    "recommended_setpoint": float(res.get("setpoint", state["target_temp"])),
                    "recommended_fan_speed": res.get("fan_speed", "Medium"),
                    "recommended_mode": res.get("mode", "Cool"),
                    "estimated_savings_pct": float(res.get("estimated_savings_pct", 0.0)),
                    "explanation": res.get("explanation", "Optimized using Gemini API."),
                    "nodes_executed": nodes
                }
            except Exception as e:
                fallback_explanation = f"[Gemini API Error: {str(e)}. Using fallback engine]"
                
        else: # openai
            try:
                from langchain_openai import ChatOpenAI
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.output_parsers import JsonOutputParser
                
                # Setup prompt template
                prompt = ChatPromptTemplate.from_messages([
                    ("system", """You are an intelligent HVAC Energy Optimizer. Your goal is to maximize energy savings while maintaining reasonable user comfort.
You will receive the current room parameters and a set of retrieved policy guidelines.
Analyze the policies and environmental conditions to output the optimal AC settings.

You MUST return your output in JSON format with EXACTLY the following structure:
{{
  "power": "ON" or "OFF",
  "setpoint": float (thermostat setting in °C, must be between 18.0 and 30.0),
  "fan_speed": "Low", "Medium", or "High",
  "mode": "Cool", "Eco", "Dry", or "Fan",
  "estimated_savings_pct": float (from 0 to 100, estimate the savings this optimization achieves relative to running normal cooling),
  "explanation": "A concise step-by-step description of why these settings were selected, referencing the applicable policies."
}}"""),
                    ("user", """### Environmental parameters:
- Indoor Temperature: {indoor_temp}°C
- Outdoor Temperature: {outdoor_temp}°C
- Target Comfort Temperature: {target_temp}°C
- Occupancy: {occupancy} (Is someone in the room?)
- Humidity: {humidity}%
- Peak tariff hour: {is_peak_hours} (Electricity rate is {electricity_rate} USD/kWh)
- Time of Day: {time_of_day}

### Retrieved Policies:
{policies_text}

Provide the optimized AC settings in JSON format:""")
                ])
                
                # Format policies
                policies_text = "\n".join([f"- {p}" for p in state["retrieved_policies"]])
                
                # Bind model
                model = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.0, openai_api_key=api_key)
                chain = prompt | model | JsonOutputParser()
                
                res = chain.invoke({
                    "indoor_temp": state["indoor_temp"],
                    "outdoor_temp": state["outdoor_temp"],
                    "target_temp": state["target_temp"],
                    "occupancy": "Yes" if state["occupancy"] else "No",
                    "humidity": state["humidity"],
                    "is_peak_hours": "Yes" if state["is_peak_hours"] else "No",
                    "electricity_rate": state["electricity_rate"],
                    "time_of_day": state["time_of_day"],
                    "policies_text": policies_text
                })
                
                return {
                    "recommended_power": res.get("power", "ON"),
                    "recommended_setpoint": float(res.get("setpoint", state["target_temp"])),
                    "recommended_fan_speed": res.get("fan_speed", "Medium"),
                    "recommended_mode": res.get("mode", "Cool"),
                    "estimated_savings_pct": float(res.get("estimated_savings_pct", 0.0)),
                    "explanation": res.get("explanation", "Optimized using OpenAI LangChain agent."),
                    "nodes_executed": nodes
                }
                
            except Exception as e:
                # Fallback to rule engine on API error
                fallback_explanation = f"[OpenAI API Error: {str(e)}. Using fallback engine]"

    # Rule-Based Heuristic Optimization Engine (Simulates LLM Cognitive Logic)
    target = state["target_temp"]
    power = "ON"
    setpoint = target
    fan = "Medium"
    mode = "Cool"
    savings = 0.0
    reasons = []

    # Parse hour of day
    hour = int(state["time_of_day"].split(":")[0])
    is_sleep_hours = hour >= 22 or hour <= 6
    
    # 1. Occupancy Policy
    if not state["occupancy"]:
        power = "OFF"
        # Eco mode thermostat fallback to keep room from baking completely (e.g. 28°C)
        setpoint = 28.0
        mode = "Eco"
        savings = 40.0
        reasons.append("Room is unoccupied. Applying Eco mode setpoint (28.0°C) to prevent cooling empty spaces, maximizing energy savings by 40%.")
    else:
        # Room is occupied, apply custom comfort-saving modes
        
        # 2. Moderate Outdoor Air Policy
        if state["outdoor_temp"] <= 24.0:
            power = "ON"
            mode = "Fan"
            fan = "Medium"
            savings = 85.0
            reasons.append(f"Outdoor temperature is moderate ({state['outdoor_temp']}°C). Switched to Fan-Only mode to utilize cool outdoor airflow, slashing compressor consumption by 85%.")
            
        # 3. High Humidity Policy
        elif state["humidity"] > 60.0:
            power = "ON"
            mode = "Dry"
            setpoint = target + 1.0  # Slightly higher setpoint due to drying comfort boost
            fan = "Low"
            savings = 20.0
            reasons.append(f"Relative humidity is high ({state['humidity']}%). Activated Dry Mode to reduce dampness. Elevated setpoint by 1°C for matching thermal comfort, saving 20% energy.")
            
        # 4. Peak Tariff Policy
        elif state["is_peak_hours"]:
            power = "ON"
            mode = "Eco"
            setpoint = target + 1.5
            fan = "Low"
            savings = 25.0
            reasons.append(f"Peak tariff pricing hours detected ({state['electricity_rate']} USD/kWh). Elevated setpoint by 1.5°C in Eco Mode to curtail active load on grid.")
            
        # 5. Sleep Hours Policy
        elif is_sleep_hours:
            power = "ON"
            mode = "Eco"
            setpoint = min(26.0, target + 1.5)
            fan = "Low"
            savings = 15.0
            reasons.append("Sleep period active. Implemented night cooling profile, raising target to 25.5°C to align with resting metabolic rate, saving 15%.")
            
        # 6. Standard comfort cooling
        else:
            power = "ON"
            mode = "Cool"
            # Set to optimal standard 24C if target is lower, or target if target is reasonable
            if target < 24.0:
                setpoint = 24.0
                savings = (24.0 - target) * 7.0  # ~7% saved per degree increased
                reasons.append(f"Standard comfort cooling active. Adjusted thermostat from preferred {target}°C to highly-efficient 24.0°C base comfort recommendation, yielding ~{round(savings)}% savings.")
            else:
                setpoint = target
                savings = 5.0
                reasons.append(f"Standard cooling maintained at target temperature ({target}°C) as it meets or exceeds energy efficiency guidelines.")

    explanation_str = " ".join(reasons)
    if fallback_explanation:
        explanation_str = f"{fallback_explanation} {explanation_str}"

    return {
        "recommended_power": power,
        "recommended_setpoint": round(setpoint, 1),
        "recommended_fan_speed": fan,
        "recommended_mode": mode,
        "estimated_savings_pct": round(savings, 1),
        "explanation": explanation_str,
        "nodes_executed": nodes
    }

# Node 3: Safety verification & constraints enforcement
def validate_safety_node(state: AgentState) -> Dict[str, Any]:
    nodes = list(state.get("nodes_executed", []))
    nodes.append("validate_safety")
    
    power = state["recommended_power"]
    setpoint = state["recommended_setpoint"]
    fan = state["recommended_fan_speed"]
    mode = state["recommended_mode"]
    explanation = state["explanation"]
    
    safety_triggered = False
    safety_notes = []
    
    # 1. Thermal comfort safety override (extreme heat)
    # If room is occupied and indoor temp > 35°C, AC must be ON in Cool mode
    if state["occupancy"] and state["indoor_temp"] >= 34.0 and power == "OFF":
        power = "ON"
        mode = "Cool"
        setpoint = 25.0
        fan = "High"
        safety_triggered = True
        safety_notes.append("Safety override: Extreme indoor temperature (>=34°C) detected in occupied space. AC powered ON to cool down immediately.")
        
    # 2. Maximum / Minimum thermostat limits
    if setpoint < 18.0:
        setpoint = 18.0
        safety_triggered = True
        safety_notes.append("Safety constraint: Thermostat setpoint clamped to minimum safe limit of 18°C.")
    elif setpoint > 30.0:
        setpoint = 30.0
        safety_triggered = True
        safety_notes.append("Safety constraint: Thermostat setpoint clamped to maximum limit of 30°C.")
        
    # Append safety comments to explanation if triggered
    if safety_triggered:
        explanation = f"[SAFETY TRIGGERED] " + " ".join(safety_notes) + " " + explanation
        
    return {
        "recommended_power": power,
        "recommended_setpoint": setpoint,
        "recommended_fan_speed": fan,
        "recommended_mode": mode,
        "explanation": explanation,
        "nodes_executed": nodes
    }

# Assemble LangGraph Workflow
def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    
    # Add Nodes
    workflow.add_node("retrieve_policies", retrieve_policies_node)
    workflow.add_node("optimize_settings", optimize_settings_node)
    workflow.add_node("validate_safety", validate_safety_node)
    
    # Connect Edges
    workflow.set_entry_point("retrieve_policies")
    workflow.add_edge("retrieve_policies", "optimize_settings")
    workflow.add_edge("optimize_settings", "validate_safety")
    workflow.add_edge("validate_safety", END)
    
    return workflow.compile()

# Compile the graph
agent_graph = build_agent_graph()

def optimize_ac_settings(sim_state: Dict[str, Any], api_key: str = "", key_type: str = "") -> Dict[str, Any]:
    """
    Executes the compiled LangGraph workflow using the simulator's current state.
    Returns the recommendations and execution trace.
    """
    initial_state: AgentState = {
        "indoor_temp": sim_state["indoor_temp"],
        "outdoor_temp": sim_state["outdoor_temp"],
        "target_temp": sim_state["target_temp"],
        "occupancy": sim_state["occupancy"],
        "humidity": sim_state["humidity"],
        "is_peak_hours": sim_state["is_peak_hours"],
        "electricity_rate": sim_state["electricity_rate"],
        "time_of_day": sim_state["time_of_day"],
        
        "api_key": api_key,
        "key_type": key_type,
        "retrieved_policies": [],
        
        "recommended_power": "ON",
        "recommended_setpoint": sim_state["target_temp"],
        "recommended_fan_speed": "Medium",
        "recommended_mode": "Cool",
        "estimated_savings_pct": 0.0,
        "explanation": "",
        
        "nodes_executed": []
    }
    
    # Run the compiled LangGraph graph
    final_state = agent_graph.invoke(initial_state)
    
    return {
        "power": final_state["recommended_power"],
        "setpoint": final_state["recommended_setpoint"],
        "fan_speed": final_state["recommended_fan_speed"],
        "mode": final_state["recommended_mode"],
        "savings_pct": final_state["estimated_savings_pct"],
        "explanation": final_state["explanation"],
        "policies": final_state["retrieved_policies"],
        "nodes_executed": final_state["nodes_executed"]
    }
