import os
import json
import re
from typing import Dict, Any, List, Optional
from backend.simulator import ACSimulator
from backend.agent import optimize_ac_settings
from backend.rag import get_policy_retriever

# Define Gemini tools structure according to the official REST API v1beta spec
GEMINI_TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "get_ac_status",
                "description": "Retrieve the current state of the AC simulator, including current indoor temperature, outdoor temperature, user comfort target, relative humidity, occupancy status, current AC settings (power, setpoint, mode, fan speed), and accumulated savings metrics."
            },
            {
                "name": "adjust_ac_parameter",
                "description": "Adjust an environmental parameter or setting in the AC simulator.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "parameter": {
                            "type": "STRING",
                            "enum": ["target_temp", "outdoor_temp", "humidity", "occupancy", "hour_of_day"],
                            "description": "The parameter to adjust."
                        },
                        "value": {
                            "type": "STRING",
                            "description": "The new value for the parameter. Use 'true'/'false' for occupancy, numeric strings for temperatures, humidity, and time."
                        }
                    },
                    "required": ["parameter", "value"]
                }
            },
            {
                "name": "trigger_optimization",
                "description": "Trigger the LangGraph optimization agent to evaluate current state against RAG policies and adjust the AC settings (power, setpoint, mode, fan speed) for maximum energy efficiency."
            },
            {
                "name": "query_energy_policies",
                "description": "Search the local policy database to retrieve guidelines and manufacturer recommendations for AC energy saving based on a query.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": "The search query (e.g., 'humidity policy', 'unoccupied comfort settings')."
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "reset_energy_metrics",
                "description": "Reset all accumulated energy metrics (Agent kWh, Baseline kWh, cost savings in USD, and CO2 reduction in kg) to zero."
            }
        ]
    }
]

# Define OpenAI tools structure
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_ac_status",
            "description": "Retrieve the current state of the AC simulator, including temperatures, target, humidity, occupancy, active settings, and accumulators."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_ac_parameter",
            "description": "Adjust an environmental parameter or setting in the AC simulator.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parameter": {
                        "type": "string",
                        "enum": ["target_temp", "outdoor_temp", "humidity", "occupancy", "hour_of_day"],
                        "description": "The parameter to adjust."
                    },
                    "value": {
                        "type": "string",
                        "description": "The new value for the parameter. Use 'true'/'false' for occupancy, numbers for temperatures."
                    }
                },
                "required": ["parameter", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_optimization",
            "description": "Trigger the LangGraph optimization agent to evaluate policies and adjust AC settings."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_energy_policies",
            "description": "Search the local policy database to retrieve guidelines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'high humidity')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reset_energy_metrics",
            "description": "Reset accumulated savings metrics."
        }
    }
]

# Core Tool Actions
def adjust_ac_parameter(simulator: ACSimulator, parameter: str, value: Any) -> str:
    try:
        if parameter == "target_temp":
            val = float(value)
            simulator.target_temp = max(16.0, min(30.0, val))
            return f"Target comfort temperature adjusted to {simulator.target_temp}°C."
        elif parameter == "outdoor_temp":
            val = float(value)
            simulator.outdoor_temp = max(-10.0, min(50.0, val))
            return f"Outdoor temperature adjusted to {simulator.outdoor_temp}°C."
        elif parameter == "humidity":
            val = float(value)
            simulator.humidity = max(10.0, min(100.0, val))
            return f"Relative humidity adjusted to {simulator.humidity}%."
        elif parameter == "occupancy":
            val = bool(value)
            simulator.occupancy = val
            status = "Occupied" if val else "Unoccupied"
            return f"Occupancy status updated to {status}."
        elif parameter == "hour_of_day":
            val = float(value)
            simulator.hour_of_day = max(0.0, min(23.99, val))
            return f"Time of day updated to {simulator.hour_of_day:02.1f} hours."
        else:
            return f"Error: Unknown parameter '{parameter}'."
    except Exception as e:
        return f"Error adjusting parameter {parameter}: {str(e)}"

def trigger_optimization(simulator: ACSimulator, api_key: str, key_type: str) -> str:
    rec = optimize_ac_settings(simulator.get_state(), api_key=api_key, key_type=key_type)
    simulator.update_settings(
        power=rec["power"],
        setpoint=rec["setpoint"],
        fan_speed=rec["fan_speed"],
        mode=rec["mode"]
    )
    return (f"Optimization complete! Applied recommendations: Power={rec['power']}, "
            f"Setpoint={rec['setpoint']}°C, Mode={rec['mode']}, Fan Speed={rec['fan_speed']}. "
            f"Estimated Savings: {rec['savings_pct']}%.")

def query_energy_policies(query: str, api_key: str) -> str:
    retriever = get_policy_retriever(api_key=api_key)
    docs = retriever.invoke(query)
    policy_texts = [f"- [{doc.metadata.get('category', 'general')}]: {doc.page_content}" for doc in docs]
    if not policy_texts:
        return "No specific policy guidelines found matching that query."
    return "Retrieved Energy Policies:\n" + "\n".join(policy_texts)

def reset_energy_metrics(simulator: ACSimulator) -> str:
    simulator.reset_accumulators()
    return "Accumulated energy savings, cost savings, and CO2 reduction metrics have been reset to zero."

def execute_tool(name: str, args: Dict[str, Any], simulator: ACSimulator, api_key: str, key_type: str) -> str:
    if name == "get_ac_status":
        state = simulator.get_state()
        return json.dumps(state)
    elif name == "adjust_ac_parameter":
        param = args.get("parameter")
        val = args.get("value")
        if isinstance(val, str):
            if val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
        return adjust_ac_parameter(simulator, param, val)
    elif name == "trigger_optimization":
        return trigger_optimization(simulator, api_key, key_type)
    elif name == "query_energy_policies":
        query = args.get("query", "comfort cooling")
        return query_energy_policies(query, api_key)
    elif name == "reset_energy_metrics":
        return reset_energy_metrics(simulator)
    else:
        return f"Error: Unknown tool '{name}'."

# Local Rule-Based Fallback Engine
def run_chat_fallback(message: str, simulator: ACSimulator, api_key: str, key_type: str) -> Dict[str, Any]:
    msg_lower = message.lower().strip()
    tool_calls = []
    
    # 1. Reset metrics
    if "reset" in msg_lower and any(kw in msg_lower for kw in ["metric", "saving", "accumulator", "cost", "co2"]):
        res = reset_energy_metrics(simulator)
        tool_calls.append({"name": "reset_energy_metrics", "args": {}, "result": res})
        response = f"I've reset all the savings metrics to zero. \n\n*Tool executed: reset_energy_metrics()*"

    # 2. Policy query
    elif any(kw in msg_lower for kw in ["policy", "policies", "guideline", "guidelines", "rule", "rules", "tariff", "tariffs", "humidity guideline", "night cooling", "manufacturer"]):
        res = query_energy_policies(message, api_key)
        tool_calls.append({"name": "query_energy_policies", "args": {"query": message}, "result": res})
        response = f"Here are the relevant energy-saving guidelines from the database:\n\n{res}\n\n*Tool executed: query_energy_policies(query='{message}')*"

    # 3a. Condition report: High humidity — set humidity high, then optimize
    elif any(kw in msg_lower for kw in ["humid", "humidity is high", "it's humid", "too humid", "very humid", "muggy", "damp"]):
        # If a specific value is given, use it; otherwise bump to 78%
        match = re.search(r"(\d+(\.\d+)?)\s*%?", msg_lower)
        new_humidity = float(match.group(1)) if match and float(match.group(1)) > 20 else 78.0
        r1 = adjust_ac_parameter(simulator, "humidity", new_humidity)
        tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "humidity", "value": new_humidity}, "result": r1})
        r2 = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": r2})
        response = (
            f"Understood — high humidity detected! I've updated the humidity to {new_humidity}% and triggered the optimizer.\n\n"
            f"{r2}\n\n"
            f"*Tools executed: adjust_ac_parameter(humidity={new_humidity}) → trigger_optimization()*"
        )

    # 3b. Condition report: Too hot indoors — bump indoor target up or trigger optimization
    elif any(kw in msg_lower for kw in ["too hot", "very hot", "it's hot", "feeling hot", "room is hot", "warm in here", "heat up", "boiling"]):
        r1 = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": r1})
        response = (
            f"I can see it's feeling too hot! I've triggered the optimization agent to maximize cooling.\n\n"
            f"{r1}\n\n"
            f"*Tool executed: trigger_optimization()*"
        )

    # 3c. Condition report: Too cold — raise setpoint and optimize
    elif any(kw in msg_lower for kw in ["too cold", "very cold", "it's cold", "feeling cold", "freezing", "chilly"]):
        new_target = min(28.0, simulator.target_temp + 2.0)
        r1 = adjust_ac_parameter(simulator, "target_temp", new_target)
        tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "target_temp", "value": new_target}, "result": r1})
        r2 = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": r2})
        response = (
            f"Room feeling too cold — I've raised the target temperature to {new_target}°C and re-optimized.\n\n"
            f"{r2}\n\n"
            f"*Tools executed: adjust_ac_parameter(target_temp={new_target}) → trigger_optimization()*"
        )

    # 3d. Condition report: No one is home / I'm leaving
    elif any(kw in msg_lower for kw in ["no one home", "nobody home", "i'm leaving", "i am leaving", "going out", "left home", "not home", "empty now", "vacating"]):
        r1 = adjust_ac_parameter(simulator, "occupancy", False)
        tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "occupancy", "value": False}, "result": r1})
        r2 = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": r2})
        response = (
            f"Got it — room marked as unoccupied. The optimizer has applied energy-saving settings.\n\n"
            f"{r2}\n\n"
            f"*Tools executed: adjust_ac_parameter(occupancy=False) → trigger_optimization()*"
        )

    # 3e. Condition report: I'm home / someone arrived
    elif any(kw in msg_lower for kw in ["i'm home", "i am home", "just arrived", "back home", "someone is here", "we're back"]):
        r1 = adjust_ac_parameter(simulator, "occupancy", True)
        tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "occupancy", "value": True}, "result": r1})
        r2 = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": r2})
        response = (
            f"Welcome back! Room is now marked as occupied and cooling settings have been optimized for comfort.\n\n"
            f"{r2}\n\n"
            f"*Tools executed: adjust_ac_parameter(occupancy=True) → trigger_optimization()*"
        )

    # 3f. Condition report: Hot outside
    elif any(kw in msg_lower for kw in ["hot outside", "outside is hot", "scorching", "it's blazing", "outdoor heat", "hot day"]):
        match = re.search(r"(\d+(\.\d+)?)", msg_lower)
        new_outdoor = float(match.group(1)) if match else 40.0
        r1 = adjust_ac_parameter(simulator, "outdoor_temp", new_outdoor)
        tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "outdoor_temp", "value": new_outdoor}, "result": r1})
        r2 = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": r2})
        response = (
            f"High outdoor temperature noted ({new_outdoor}°C). Optimizer re-run with updated conditions.\n\n"
            f"{r2}\n\n"
            f"*Tools executed: adjust_ac_parameter(outdoor_temp={new_outdoor}) → trigger_optimization()*"
        )

    # 3g. Condition report: Cool outside / breezy
    elif any(kw in msg_lower for kw in ["cool outside", "outside is cool", "breezy", "mild outside", "pleasant outside", "cooler now"]):
        match = re.search(r"(\d+(\.\d+)?)", msg_lower)
        new_outdoor = float(match.group(1)) if match else 22.0
        r1 = adjust_ac_parameter(simulator, "outdoor_temp", new_outdoor)
        tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "outdoor_temp", "value": new_outdoor}, "result": r1})
        r2 = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": r2})
        response = (
            f"Cool outdoor conditions noted ({new_outdoor}°C). The optimizer may switch to Fan-Only mode to save maximum energy.\n\n"
            f"{r2}\n\n"
            f"*Tools executed: adjust_ac_parameter(outdoor_temp={new_outdoor}) → trigger_optimization()*"
        )

    # 4. Adjust AC target temp (explicit set command)
    elif any(kw in msg_lower for kw in ["set target", "target temp", "comfort temp", "set temperature", "set thermostat"]):
        match = re.search(r"(\d+(\.\d+)?)", msg_lower)
        if match:
            temp = float(match.group(1))
            res = adjust_ac_parameter(simulator, "target_temp", temp)
            tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "target_temp", "value": temp}, "result": res})
            response = f"Sure, I've adjusted the target comfort temperature. \n\n*Tool executed: adjust_ac_parameter(parameter='target_temp', value={temp})*"
        else:
            response = "I detected you wanted to set the target temperature, but I couldn't find a temperature value. Please try: 'set target temperature to 24'."

    # 5. Adjust occupancy (explicit toggle)
    elif any(kw in msg_lower for kw in ["occup", "empty", "someone", "vacant", "leave", "left", "arrive", "home"]):
        is_occupied = True
        if any(kw in msg_lower for kw in ["unoccupied", "empty", "no one", "vacant", "leave", "left", "away"]):
            is_occupied = False
        res = adjust_ac_parameter(simulator, "occupancy", is_occupied)
        tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "occupancy", "value": is_occupied}, "result": res})
        status_str = "occupied" if is_occupied else "unoccupied"
        response = f"I have updated the simulator room occupancy status to {status_str}. \n\n*Tool executed: adjust_ac_parameter(parameter='occupancy', value={is_occupied})*"

    # 6. Adjust outdoor temp (explicit set command)
    elif "outdoor" in msg_lower and any(kw in msg_lower for kw in ["set", "change", "adjust", "to"]):
        match = re.search(r"(\d+(\.\d+)?)", msg_lower)
        if match:
            temp = float(match.group(1))
            res = adjust_ac_parameter(simulator, "outdoor_temp", temp)
            tool_calls.append({"name": "adjust_ac_parameter", "args": {"parameter": "outdoor_temp", "value": temp}, "result": res})
            response = f"I've adjusted the outdoor temperature. \n\n*Tool executed: adjust_ac_parameter(parameter='outdoor_temp', value={temp})*"
        else:
            response = "I couldn't identify the outdoor temperature value. Try 'set outdoor temp to 30'."

    # 7. Run optimization (explicit request)
    elif any(kw in msg_lower for kw in ["optimize", "run optimization", "run optimizer", "evaluate policies", "adjust ac settings"]):
        res = trigger_optimization(simulator, api_key, key_type)
        tool_calls.append({"name": "trigger_optimization", "args": {}, "result": res})
        response = f"I've triggered the optimization graph. Here are the recommendations:\n\n{res}\n\n*Tool executed: trigger_optimization()*"
        
    # 7. Get status / general inquiry
    else:
        state = simulator.get_state()
        res = json.dumps(state, indent=2)
        tool_calls.append({"name": "get_ac_status", "args": {}, "result": res})
        response = (
            f"Here is the current HVAC system status:\n\n"
            f"* **Indoor Temperature**: {state['indoor_temp']}°C (Baseline target: {state['baseline_indoor_temp']}°C)\n"
            f"* **Outdoor Temperature**: {state['outdoor_temp']}°C\n"
            f"* **Comfort Target**: {state['target_temp']}°C\n"
            f"* **Occupancy**: {'Occupied' if state['occupancy'] else 'Unoccupied'}\n"
            f"* **Humidity**: {state['humidity']}%\n"
            f"* **AC Settings**: Power is **{state['ac_power']}**, setpoint is **{state['ac_setpoint']}°C** ({state['ac_mode']} mode, {state['ac_fan_speed']} fan)\n"
            f"* **Accumulated Savings**: **${state['savings_usd']}** ({state['agent_energy_kwh']} kWh vs baseline {state['baseline_energy_kwh']} kWh, CO₂ saved: {state['co2_saved_kg']} kg)\n\n"
            f"*(Note: Running in local fallback mode. Enter a Gemini or OpenAI API key to enable natural conversational responses.)*"
        )
        
    return {
        "response": response,
        "tool_calls": tool_calls
    }

# LLM-Based Chat Agent: OpenAI Implementation
def run_openai_chat(message: str, history: List[Dict[str, str]], api_key: str, simulator: ACSimulator) -> Dict[str, Any]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    
    system_msg = {
        "role": "system",
        "content": "You are SmartAC Conversational Assistant. You are an expert HVAC control agent that can read and write parameters of the AC simulator using tools, retrieve energy policies, and run energy-efficiency optimization. Answer user questions concisely, reference policies if relevant, and call tools as needed."
    }
    
    messages = [system_msg]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    
    tool_calls_executed = []
    
    for _ in range(5):
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.0
        )
        
        assistant_message = response.choices[0].message
        
        if assistant_message.tool_calls:
            # Append assistant's intent to messages
            messages.append(assistant_message)
            
            for tool_call in assistant_message.tool_calls:
                t_name = tool_call.function.name
                t_args = json.loads(tool_call.function.arguments)
                
                result = execute_tool(t_name, t_args, simulator, api_key, "openai")
                tool_calls_executed.append({"name": t_name, "args": t_args, "result": result})
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": t_name,
                    "content": result
                })
        else:
            return {
                "response": assistant_message.content,
                "tool_calls": tool_calls_executed
            }
            
    return {
        "response": "Error: Too many tool call cycles.",
        "tool_calls": tool_calls_executed
    }

# LLM-Based Chat Agent: Google Gemini Implementation via Direct REST API
def run_gemini_chat(message: str, history: List[Dict[str, str]], api_key: str, simulator: ACSimulator) -> Dict[str, Any]:
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    system_instruction = "You are SmartAC Conversational Assistant. You are an expert HVAC control agent that can read and write parameters of the AC simulator using tools, retrieve energy policies, and run energy-efficiency optimization. Answer user questions concisely, reference policies if relevant, and call tools as needed."
    
    # Rebuild conversation contents for Gemini
    contents = []
    for h in history:
        role = "user" if h["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": h["content"]}]
        })
        
    contents.append({
        "role": "user",
        "parts": [{"text": message}]
    })
    
    tool_calls_executed = []
    
    for cycle in range(5):
        payload = {
            "contents": contents,
            "tools": GEMINI_TOOLS,
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": 0.0
            }
        }
        
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        response.raise_for_status()
        res_json = response.json()
        
        candidate = res_json["candidates"][0]
        model_content = candidate["content"]
        
        # Keep track of model response in contents
        contents.append(model_content)
        
        parts = model_content.get("parts", [])
        has_function_call = False
        
        for part in parts:
            if "functionCall" in part:
                has_function_call = True
                f_call = part["functionCall"]
                t_name = f_call["name"]
                t_args = f_call.get("args", {})
                
                # Execute the tool
                result = execute_tool(t_name, t_args, simulator, api_key, "gemini")
                tool_calls_executed.append({"name": t_name, "args": t_args, "result": result})
                
                # Append tool response
                contents.append({
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": t_name,
                                "response": {
                                    "output": result
                                }
                            }
                        }
                    ]
                })
        
        if not has_function_call:
            text_response = "".join([part.get("text", "") for part in parts])
            return {
                "response": text_response,
                "tool_calls": tool_calls_executed
            }
            
    return {
        "response": "Error: Too many tool call cycles.",
        "tool_calls": tool_calls_executed
    }

# Main Entrypoint
def run_chat_agent(message: str, history: List[Dict[str, str]], api_key: str, key_type: str, simulator: ACSimulator) -> Dict[str, Any]:
    api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    
    if api_key and not key_type:
        key_type = "gemini" if api_key.startswith("AIzaSy") else "openai"
        
    if not api_key:
        return run_chat_fallback(message, simulator, "", "")
        
    if key_type == "gemini":
        try:
            return run_gemini_chat(message, history, api_key, simulator)
        except Exception as e:
            fallback_res = run_chat_fallback(message, simulator, api_key, "gemini")
            fallback_res["response"] = f"[Gemini API Error: {str(e)}. Running fallback assistant] " + fallback_res["response"]
            return fallback_res
    else:
        try:
            return run_openai_chat(message, history, api_key, simulator)
        except Exception as e:
            fallback_res = run_chat_fallback(message, simulator, api_key, "openai")
            fallback_res["response"] = f"[OpenAI API Error: {str(e)}. Running fallback assistant] " + fallback_res["response"]
            return fallback_res
