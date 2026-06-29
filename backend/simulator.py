import math
import random
from typing import Dict, Any

class ACSimulator:
    def __init__(self):
        # Current environmental parameters
        self.indoor_temp = 26.5          # °C
        self.outdoor_temp = 33.0         # °C
        self.target_temp = 22.0          # °C (User's preferred comfort temperature)
        self.occupancy = True            # True = occupied, False = empty
        self.humidity = 65.0             # % relative humidity
        
        # Electricity tariffs
        self.hour_of_day = 12            # 24-hour clock
        self.electricity_rate = 0.15     # USD per kWh (Standard)
        
        # Optimization settings set by the agent
        self.ac_power = "ON"             # "ON" or "OFF"
        self.ac_setpoint = 23.0          # °C (The actual setpoint applied by agent)
        self.ac_fan_speed = "Medium"     # "Low", "Medium", "High"
        self.ac_mode = "Cool"            # "Cool", "Eco", "Dry", "Fan"

        # Accumulators for metrics
        self.cumulative_agent_energy = 0.0      # kWh
        self.cumulative_baseline_energy = 0.0   # kWh
        self.cumulative_savings_usd = 0.0       # USD
        self.cumulative_co2_saved_kg = 0.0      # kg CO2 (approx 0.4 kg CO2 per kWh)
        
        # Keep track of baseline AC state (always runs at target_temp in Cool mode if occupied, else off)
        self.baseline_indoor_temp = 26.5

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state of the simulator."""
        time_str = f"{int(self.hour_of_day):02d}:00"
        is_peak = 14 <= self.hour_of_day <= 18  # Peak hours 2 PM to 6 PM
        
        return {
            "indoor_temp": round(self.indoor_temp, 2),
            "baseline_indoor_temp": round(self.baseline_indoor_temp, 2),
            "outdoor_temp": round(self.outdoor_temp, 2),
            "target_temp": round(self.target_temp, 2),
            "occupancy": self.occupancy,
            "humidity": round(self.humidity, 1),
            "hour_of_day": self.hour_of_day,
            "time_of_day": time_str,
            "is_peak_hours": is_peak,
            "electricity_rate": round(self.electricity_rate, 2),
            "ac_power": self.ac_power,
            "ac_setpoint": round(self.ac_setpoint, 2),
            "ac_fan_speed": self.ac_fan_speed,
            "ac_mode": self.ac_mode,
            "agent_energy_kwh": round(self.cumulative_agent_energy, 4),
            "baseline_energy_kwh": round(self.cumulative_baseline_energy, 4),
            "savings_usd": round(self.cumulative_savings_usd, 4),
            "co2_saved_kg": round(self.cumulative_co2_saved_kg, 4)
        }

    def update_settings(self, power: str, setpoint: float, fan_speed: str, mode: str):
        """Update the AC parameters as instructed by the agent."""
        self.ac_power = power
        self.ac_setpoint = max(18.0, min(30.0, setpoint))
        self.ac_fan_speed = fan_speed
        self.ac_mode = mode

    def step(self):
        """
        Advance simulation by 1 step (representing 5 minutes of real time).
        Updates temperatures and power consumption for both Agent-Controlled and Baseline ACs.
        """
        step_minutes = 5.0
        hours = step_minutes / 60.0
        
        # --- Time and Environment progression ---
        # Slowly increment hour of day
        self.hour_of_day = (self.hour_of_day + step_minutes / 60.0) % 24
        
        # Vary outdoor temp slightly based on time of day (sine wave model + slight noise)
        # Peak outdoor temp at 3 PM (15:00), minimum at 4 AM (04:00)
        time_rad = (self.hour_of_day - 15) * 2 * 3.14159 / 24
        base_outdoor = 31.0 if (10 <= self.hour_of_day <= 19) else 26.0
        self.outdoor_temp = base_outdoor + 4.0 * math.cos(time_rad) + random.uniform(-0.2, 0.2)
        
        # Peak pricing rate between 2 PM and 6 PM
        if 14 <= self.hour_of_day <= 18:
            self.electricity_rate = 0.35  # Peak rate (USD/kWh)
        else:
            self.electricity_rate = 0.15  # Standard rate (USD/kWh)
            
        # Fluctuating indoor humidity (AC lowers it, outdoor influences it)
        humidity_drift = random.uniform(-0.5, 0.5)
        self.humidity = max(30.0, min(90.0, self.humidity + humidity_drift))

        # --- THERMAL PROCESS MODEL ---
        # Thermal characteristics
        thermal_loss_factor = 0.03  # How fast indoor temp moves towards outdoor temp per step
        occupancy_heat_load = 0.1   # Heat contribution (°C) from occupants per step if no cooling
        
        # 1. Simulate AGENT-CONTROLLED room temperature
        temp_diff_agent = self.outdoor_temp - self.indoor_temp
        self.indoor_temp += temp_diff_agent * thermal_loss_factor
        if self.occupancy:
            self.indoor_temp += occupancy_heat_load * random.uniform(0.8, 1.2)
            
        # Cooling effect of AGENT AC
        agent_power_kw = 0.0
        if self.ac_power == "ON":
            cooling_strength = 0.0
            
            # Determine cooling capacity and power usage based on mode & fan
            if self.ac_mode == "Cool":
                cooling_strength = 0.4 if self.ac_fan_speed == "High" else (0.3 if self.ac_fan_speed == "Medium" else 0.2)
                base_power = 1.8 if self.ac_fan_speed == "High" else (1.5 if self.ac_fan_speed == "Medium" else 1.2)
            elif self.ac_mode == "Eco":
                cooling_strength = 0.28  # Moderate cooling
                base_power = 0.9        # High efficiency
            elif self.ac_mode == "Dry":
                cooling_strength = 0.22  # Lower cooling, focus on dehumidification
                base_power = 1.0
                self.humidity = max(40.0, self.humidity - 2.5) # Dries the air significantly
            elif self.ac_mode == "Fan":
                cooling_strength = 0.02  # Almost no thermal change
                base_power = 0.15       # Minimal fan-only power
                
            # If room is warmer than setpoint, compressor runs
            if self.indoor_temp > self.ac_setpoint:
                # Compressor power scale depends on temperature gap (up to 30% extra capacity)
                gap = self.indoor_temp - self.ac_setpoint
                power_mult = min(1.3, max(0.6, gap * 0.4))
                
                # Eco mode limits max power draw
                if self.ac_mode == "Eco":
                    power_mult = min(1.0, power_mult)
                    
                self.indoor_temp -= cooling_strength * power_mult
                agent_power_kw = base_power * power_mult
            else:
                # Compressor cycles off, only fan runs
                self.indoor_temp = max(self.ac_setpoint - 0.5, self.indoor_temp - 0.05)
                agent_power_kw = 0.15  # Fan-only baseline
        
        # 2. Simulate BASELINE room temperature
        # Baseline is running AC at standard "Cool" mode, "Medium" fan, and setpoint = target_temp
        # only if occupied (otherwise baseline turns it off to be fair, though sometimes users leave it on)
        temp_diff_base = self.outdoor_temp - self.baseline_indoor_temp
        self.baseline_indoor_temp += temp_diff_base * thermal_loss_factor
        if self.occupancy:
            self.baseline_indoor_temp += occupancy_heat_load
            
        baseline_power_kw = 0.0
        # If occupied, baseline AC is ON at target_temp in Cool mode
        if self.occupancy:
            baseline_cooling = 0.3  # Medium fan strength
            baseline_base_power = 1.5
            
            if self.baseline_indoor_temp > self.target_temp:
                gap = self.baseline_indoor_temp - self.target_temp
                power_mult = min(1.3, max(0.6, gap * 0.4))
                self.baseline_indoor_temp -= baseline_cooling * power_mult
                baseline_power_kw = baseline_base_power * power_mult
            else:
                self.baseline_indoor_temp = max(self.target_temp - 0.5, self.baseline_indoor_temp - 0.05)
                baseline_power_kw = 0.15
        else:
            # Unoccupied baseline: AC is OFF
            pass

        # --- ENERGY & COST METRICS ACCUMULATION ---
        step_agent_energy = agent_power_kw * hours
        step_baseline_energy = baseline_power_kw * hours
        
        self.cumulative_agent_energy += step_agent_energy
        self.cumulative_baseline_energy += step_baseline_energy
        
        step_agent_cost = step_agent_energy * self.electricity_rate
        step_baseline_cost = step_baseline_energy * self.electricity_rate
        
        step_savings = step_baseline_cost - step_agent_cost
        self.cumulative_savings_usd += step_savings
        
        # CO2 savings: ~0.4 kg CO2 per kWh saved
        self.cumulative_co2_saved_kg += (step_baseline_energy - step_agent_energy) * 0.4
        
        # Ensure values don't go negative (if agent temporarily uses more due to pre-cooling, savings can drop, but aggregate is positive)
        self.cumulative_savings_usd = max(-5.0, self.cumulative_savings_usd)
        self.cumulative_co2_saved_kg = max(-2.0, self.cumulative_co2_saved_kg)

    def reset_accumulators(self):
        self.cumulative_agent_energy = 0.0
        self.cumulative_baseline_energy = 0.0
        self.cumulative_savings_usd = 0.0
        self.cumulative_co2_saved_kg = 0.0
