"""
AI-Powered Collision Risk Analysis using NVIDIA NIM
=====================================================

Integrates with NVIDIA's NIM API (build.nvidia.com) to provide:
- Natural language risk assessment of conjunction events
- Intelligent maneuver recommendations with explanations
- Real-time scenario narration for the dashboard
- Orbital environment health summaries

Uses the OpenAI-compatible API at integrate.api.nvidia.com/v1
with NVIDIA's Llama Nemotron reasoning models.
"""

import os
import json
from typing import Dict, List, Optional
from dataclasses import dataclass

from openai import OpenAI

from .utils import (
    R_EARTH, MU_EARTH, CATASTROPHIC_ENERGY,
    StateVector, Spacecraft, Conjunction, Maneuver,
    state_to_coe, orbital_period
)
from .conjunction import estimate_debris_count, debris_lifetime


# ============================================================================
# NVIDIA NIM CLIENT
# ============================================================================

# Model hosted on build.nvidia.com
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"


def _get_client() -> OpenAI:
    """
    Create an OpenAI-compatible client pointed at NVIDIA NIM.

    Requires NVIDIA_API_KEY environment variable (from build.nvidia.com).
    """
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "NVIDIA_API_KEY not set. Get one free at https://build.nvidia.com"
        )

    return OpenAI(
        base_url=NVIDIA_NIM_BASE_URL,
        api_key=api_key
    )


def _chat(system_prompt: str, user_prompt: str,
          temperature: float = 0.3, max_tokens: int = 1024) -> str:
    """
    Send a chat completion request to NVIDIA NIM.

    Parameters
    ----------
    system_prompt : str
        System context for the model
    user_prompt : str
        The user query / data to analyze
    temperature : float
        Sampling temperature (lower = more deterministic)
    max_tokens : int
        Maximum response length

    Returns
    -------
    str
        Model response text
    """
    client = _get_client()

    completion = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=temperature,
        top_p=0.7,
        max_tokens=max_tokens,
        stream=False
    )

    return completion.choices[0].message.content


# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

SYSTEM_PROMPT_RISK_ANALYST = """You are an expert Space Situational Awareness (SSA) analyst working in a satellite collision avoidance operations center. You analyze conjunction data and provide clear, actionable risk assessments.

Your analysis style:
- Lead with the risk verdict (CRITICAL / HIGH / MODERATE / LOW)
- Explain the physics in plain English
- Quantify consequences (debris count, affected orbits, cascade potential)
- Recommend specific actions with priorities
- Note any uncertainties or assumptions

Use precise numbers from the data provided. Reference orbital mechanics concepts when relevant but keep language accessible to mission operators."""

SYSTEM_PROMPT_MANEUVER_ADVISOR = """You are a spacecraft flight dynamics engineer specializing in collision avoidance maneuvers. Given conjunction data and spacecraft state, you recommend optimal avoidance strategies.

Your recommendations include:
- Maneuver timing (why earlier/later is better for this case)
- Burn direction and magnitude rationale
- Fuel budget implications (remaining lifetime impact)
- Alternative strategies if primary fails
- Post-maneuver verification criteria

Be specific about trade-offs. A mission operator should be able to act on your recommendation directly."""

SYSTEM_PROMPT_NARRATOR = """You are narrating a real-time satellite collision scenario for a mission control visualization dashboard. Your tone is urgent but professional, like a mission commentator during a critical space operation.

Guidelines:
- Keep messages concise (2-3 sentences max)
- Build tension appropriately (detection → analysis → decision → execution → resolution)
- Use specific numbers from the data
- Reference real space operations terminology (TCA, Pc, delta-v, miss distance)
- Match the emotional weight of the situation (catastrophic collision vs. routine avoidance)"""

SYSTEM_PROMPT_ENVIRONMENT = """You are an orbital environment analyst assessing the long-term sustainability of orbital shells. You evaluate Kessler syndrome risk, debris population trends, and recommend policy/operational interventions.

Focus on:
- Which altitude bands are most at risk
- Rate of debris accumulation vs. natural removal
- Impact of specific collision events on long-term stability
- Concrete recommendations (deorbit timelines, avoidance zone proposals)
- Historical context (Cosmos-Iridium 2009, Chinese ASAT 2007) for comparison"""


# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================


def analyze_conjunction(conjunction: Conjunction,
                        sc1: Spacecraft, sc2: Spacecraft) -> Dict:
    """
    AI-powered analysis of a conjunction event.

    Provides natural language risk assessment, consequence modeling,
    and action recommendations.

    Parameters
    ----------
    conjunction : Conjunction
        The conjunction event to analyze
    sc1 : Spacecraft
        First object
    sc2 : Spacecraft
        Second object

    Returns
    -------
    dict
        Analysis with keys: risk_level, summary, consequences,
        recommendations, raw_response
    """
    # Compute derived quantities for context
    coe1 = state_to_coe(sc1.state)
    coe2 = state_to_coe(sc2.state)
    alt1 = coe1.a - R_EARTH
    alt2 = coe2.a - R_EARTH

    # Collision energy
    combined_mass = sc1.mass + sc2.mass
    smaller_mass = min(sc1.mass, sc2.mass)
    larger_mass = max(sc1.mass, sc2.mass)
    energy_per_kg = 0.5 * smaller_mass * (conjunction.relative_velocity * 1000) ** 2 / larger_mass
    is_catastrophic = energy_per_kg > CATASTROPHIC_ENERGY

    # Debris estimates
    n_debris = estimate_debris_count(sc1.mass, sc2.mass, conjunction.relative_velocity)
    lifetime = debris_lifetime((alt1 + alt2) / 2)

    # Fuel state
    fuel1 = sc1.delta_v_budget - sc1.delta_v_used
    fuel2 = sc2.delta_v_budget - sc2.delta_v_used

    user_prompt = f"""Analyze this conjunction event:

CONJUNCTION DATA:
- Time to closest approach (TCA): {conjunction.tca / 3600:.1f} hours from now
- Miss distance: {conjunction.miss_distance:.3f} km ({conjunction.miss_distance * 1000:.0f} meters)
- Relative velocity: {conjunction.relative_velocity:.2f} km/s ({conjunction.relative_velocity * 1000:.0f} m/s)
- Probability of collision (Pc): {conjunction.probability_of_collision:.2e}
- Risk score: {conjunction.risk_score:.4f}

OBJECT 1 ({sc1.name or sc1.id}):
- Mass: {sc1.mass:.0f} kg
- Altitude: {alt1:.0f} km
- Maneuverable: {sc1.maneuverable}
- Fuel remaining: {fuel1:.1f} m/s of {sc1.delta_v_budget:.0f} m/s total

OBJECT 2 ({sc2.name or sc2.id}):
- Mass: {sc2.mass:.0f} kg
- Altitude: {alt2:.0f} km
- Maneuverable: {sc2.maneuverable}
- Fuel remaining: {fuel2:.1f} m/s of {sc2.delta_v_budget:.0f} m/s total

DERIVED ANALYSIS:
- Impact energy: {energy_per_kg:.0f} J/kg (catastrophic threshold: 40,000 J/kg)
- Catastrophic collision: {'YES' if is_catastrophic else 'NO'}
- Expected debris (>10cm): {n_debris:.0f} fragments
- Debris orbital lifetime: {lifetime:.1f} years
- Combined mass at risk: {combined_mass:.0f} kg

Provide your risk assessment, consequences if collision occurs, and recommended actions."""

    try:
        response = _chat(SYSTEM_PROMPT_RISK_ANALYST, user_prompt)

        return {
            "status": "success",
            "risk_level": "CRITICAL" if conjunction.probability_of_collision >= 1e-4
                          else "HIGH" if conjunction.probability_of_collision >= 1e-5
                          else "MODERATE" if conjunction.probability_of_collision >= 1e-6
                          else "LOW",
            "is_catastrophic": is_catastrophic,
            "debris_count": int(n_debris),
            "debris_lifetime_years": float(lifetime),
            "energy_per_kg": float(energy_per_kg),
            "analysis": response,
            "conjunction_id": f"{conjunction.obj1_id}_{conjunction.obj2_id}"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "conjunction_id": f"{conjunction.obj1_id}_{conjunction.obj2_id}"
        }


def recommend_maneuver(conjunction: Conjunction,
                       spacecraft: Spacecraft,
                       target: Spacecraft,
                       planned_maneuver: Optional[Maneuver] = None) -> Dict:
    """
    AI-powered maneuver recommendation.

    Takes conjunction data and an optional already-computed maneuver,
    and provides intelligent commentary and alternatives.

    Parameters
    ----------
    conjunction : Conjunction
        The threat conjunction
    spacecraft : Spacecraft
        The spacecraft that will maneuver
    target : Spacecraft
        The other object (may be debris/non-maneuverable)
    planned_maneuver : Maneuver, optional
        A previously computed maneuver to evaluate

    Returns
    -------
    dict
        Recommendation with natural language explanation
    """
    coe = state_to_coe(spacecraft.state)
    altitude = coe.a - R_EARTH
    period = orbital_period(coe.a)
    fuel_remaining = spacecraft.delta_v_budget - spacecraft.delta_v_used
    orbits_to_tca = conjunction.tca / period

    maneuver_info = ""
    if planned_maneuver:
        maneuver_info = f"""
COMPUTED MANEUVER:
- Delta-v: {planned_maneuver.fuel_cost:.2f} m/s
- Direction (RTN): R={planned_maneuver.delta_v[0]*1000:.2f}, T={planned_maneuver.delta_v[1]*1000:.2f}, N={planned_maneuver.delta_v[2]*1000:.2f} m/s
- Execution time: {planned_maneuver.time / 3600:.1f} hours from now
- Fuel cost as % of remaining: {planned_maneuver.fuel_cost / max(fuel_remaining, 0.1) * 100:.1f}%
"""

    user_prompt = f"""Recommend an avoidance maneuver for this conjunction:

THREAT:
- TCA: {conjunction.tca / 3600:.1f} hours ({orbits_to_tca:.1f} orbits away)
- Miss distance: {conjunction.miss_distance * 1000:.0f} meters
- Relative velocity: {conjunction.relative_velocity:.1f} km/s
- Pc: {conjunction.probability_of_collision:.2e}

MANEUVERING SPACECRAFT ({spacecraft.name or spacecraft.id}):
- Mass: {spacecraft.mass:.0f} kg
- Altitude: {altitude:.0f} km
- Orbital period: {period / 60:.0f} minutes
- Fuel remaining: {fuel_remaining:.1f} m/s ({fuel_remaining / spacecraft.delta_v_budget * 100:.0f}% of lifetime budget)
- Maneuverable: {spacecraft.maneuverable}

TARGET OBJECT ({target.name or target.id}):
- Mass: {target.mass:.0f} kg
- Maneuverable: {target.maneuverable}
{maneuver_info}
Provide your maneuver recommendation including timing rationale, direction preference, fuel impact assessment, and verification criteria."""

    try:
        response = _chat(SYSTEM_PROMPT_MANEUVER_ADVISOR, user_prompt)

        return {
            "status": "success",
            "spacecraft_id": spacecraft.id,
            "conjunction_id": f"{conjunction.obj1_id}_{conjunction.obj2_id}",
            "fuel_remaining_ms": float(fuel_remaining),
            "orbits_to_tca": float(orbits_to_tca),
            "recommendation": response
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "spacecraft_id": spacecraft.id
        }


def narrate_scenario_event(event: Dict, scenario_metadata: Dict) -> Dict:
    """
    Generate AI narration for a collision scenario event.

    Used by the dashboard to provide real-time commentary during
    animated collision/avoidance scenarios.

    Parameters
    ----------
    event : dict
        Scenario event with type, message, data
    scenario_metadata : dict
        Overall scenario context (altitude, velocities, masses)

    Returns
    -------
    dict
        Narration with commentary field
    """
    user_prompt = f"""Generate mission control narration for this event:

SCENARIO: {scenario_metadata.get('object1_type', 'Spacecraft')} vs {scenario_metadata.get('object2_type', 'Object')} at {scenario_metadata.get('altitude_km', 0):.0f} km altitude

EVENT:
- Type: {event.get('type', 'unknown')}
- Message: {event.get('message', '')}
- Data: {json.dumps(event.get('data', {}), indent=2)}

CONTEXT:
- Relative velocity: {scenario_metadata.get('relative_velocity_kms', 0):.1f} km/s
- Object 1 mass: {scenario_metadata.get('mass1_kg', 0):.0f} kg
- Object 2 mass: {scenario_metadata.get('mass2_kg', 0):.0f} kg
- Maneuver capability: {scenario_metadata.get('maneuver_dv_ms', 0):.1f} m/s available

Provide a brief (2-3 sentence) mission control style narration for this moment."""

    try:
        response = _chat(SYSTEM_PROMPT_NARRATOR, user_prompt,
                         temperature=0.5, max_tokens=256)
        return {
            "status": "success",
            "event_type": event.get("type"),
            "narration": response
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "event_type": event.get("type")
        }


def assess_orbital_environment(shells: List[Dict],
                                debris_data: List[Dict],
                                risk_metrics: Dict) -> Dict:
    """
    AI assessment of overall orbital environment health.

    Evaluates Kessler syndrome risk, identifies problem altitude bands,
    and recommends interventions.

    Parameters
    ----------
    shells : list of dict
        Orbital shell data (altitude bands with object counts, collision rates)
    debris_data : list of dict
        Recent/predicted debris events
    risk_metrics : dict
        Global risk metrics summary

    Returns
    -------
    dict
        Environment assessment with recommendations
    """
    # Find unstable shells
    unstable = [s for s in shells if s.get('is_unstable', False)]
    densest = sorted(shells, key=lambda s: s.get('object_count', 0), reverse=True)[:3]

    user_prompt = f"""Assess the orbital environment health:

GLOBAL METRICS:
- Total tracked objects: {risk_metrics.get('total_spacecraft', 0)}
- Active conjunctions: {risk_metrics.get('total_conjunctions', 0)}
- Critical conjunctions (Pc > 1e-4): {risk_metrics.get('critical_conjunctions', 0)}
- High-risk conjunctions (Pc > 1e-5): {risk_metrics.get('high_risk_conjunctions', 0)}
- Planned avoidance maneuvers: {risk_metrics.get('maneuvers_planned', 0)}
- Total mass at risk: {risk_metrics.get('total_mass_kg', 0):.0f} kg
- Average altitude: {risk_metrics.get('avg_altitude_km', 0):.0f} km

UNSTABLE SHELLS (debris generation > removal):
{json.dumps(unstable, indent=2) if unstable else "None currently unstable"}

DENSEST ALTITUDE BANDS:
{json.dumps(densest[:3], indent=2)}

RECENT/PREDICTED DEBRIS EVENTS:
{json.dumps(debris_data[:5], indent=2) if debris_data else "No recent events"}

Provide your assessment of:
1. Current orbital environment stability
2. Kessler syndrome risk level and timeline
3. Most concerning altitude bands
4. Recommended operational and policy interventions"""

    try:
        response = _chat(SYSTEM_PROMPT_ENVIRONMENT, user_prompt,
                         temperature=0.3, max_tokens=1500)
        return {
            "status": "success",
            "unstable_shell_count": len(unstable),
            "total_objects": risk_metrics.get('total_spacecraft', 0),
            "critical_conjunctions": risk_metrics.get('critical_conjunctions', 0),
            "assessment": response
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================================================
# BATCH ANALYSIS
# ============================================================================


def analyze_top_risks(spacecraft_list: List[Spacecraft],
                      conjunctions: List[Conjunction],
                      top_n: int = 3) -> List[Dict]:
    """
    Analyze the top N riskiest conjunctions with AI.

    Parameters
    ----------
    spacecraft_list : list of Spacecraft
        All spacecraft
    conjunctions : list of Conjunction
        All conjunctions (will be sorted by risk)
    top_n : int
        Number of top risks to analyze

    Returns
    -------
    list of dict
        AI analysis for each top conjunction
    """
    sc_dict = {sc.id: sc for sc in spacecraft_list}
    sorted_conj = sorted(conjunctions, key=lambda c: c.risk_score, reverse=True)

    results = []
    for conj in sorted_conj[:top_n]:
        sc1 = sc_dict.get(conj.obj1_id)
        sc2 = sc_dict.get(conj.obj2_id)
        if sc1 and sc2:
            analysis = analyze_conjunction(conj, sc1, sc2)
            results.append(analysis)

    return results
