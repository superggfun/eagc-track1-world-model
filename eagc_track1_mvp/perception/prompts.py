PROMPT_VERSION = "v0.4.4"

EXTRACTOR_SYSTEM_PROMPT = """You are a text-only perception module for an embodied agent.
Return one valid JSON object only. Do not use markdown fences, prose, explanations, or comments.
The JSON object must include these top-level keys: rooms, topology, objects, relations, states, affordances, uncertainty.
Do not generate plans or task actions; planning actions are produced by the planner, not perception.
Only extract information grounded in the observation. Do not invent unrelated objects.
For uncertain or inferred information, include status and confidence fields."""


def build_extraction_prompt(observation: str, task: str) -> str:
    return f"""
Task: {task}

Observation:
{observation}

Return exactly this JSON shape:
{{
  "rooms": ["room_name"],
  "topology": [
    {{"room": "room_name", "visited": true, "frontiers": ["frontier_or_exit_name"], "status": "observed", "confidence": 0.0}}
  ],
  "objects": [
    {{
      "name": "object_name",
      "category": "object|furniture|door|container|tool|surface|inferred_support",
      "location": {{"room": "room_name", "region": "region_name", "support": "support_object", "status": "known|unknown|inferred", "confidence": 0.0}},
      "state": "observed|inferred|unknown"
    }}
  ],
  "relations": [
    {{"subject": "object", "relation": "on|near|beside|inside|under|at", "object": "object_or_place", "status": "active|stale|inferred|uncertain", "confidence": 0.0, "observed_at_step": 1}}
  ],
  "states": [
    {{"entity": "object_or_agent", "attribute": "attribute_name", "value": "value"}}
  ],
  "affordances": [
    {{"object": "object_name", "affordance": "portable|openable|support|container|usable_tool", "status": "known|inferred|uncertain", "confidence": 0.0}}
  ],
  "uncertainty": [
    {{"item": "object_or_state", "reason": "short reason", "level": "low|medium|high", "status": "uncertain|inferred", "confidence": 0.0}}
  ]
}}
"""
