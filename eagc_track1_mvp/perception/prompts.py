EXTRACTOR_SYSTEM_PROMPT = """You are a perception module for an embodied agent.
Extract a compact world-model update from text-only indoor observations.
Return valid JSON only. Do not include markdown or commentary."""


def build_extraction_prompt(observation: str, task: str) -> str:
    return f"""
Task: {task}

Observation:
{observation}

Return exactly this JSON shape:
{{
  "rooms": ["room_name"],
  "objects": [
    {{"name": "object_name", "type": "object", "room": "room_name"}}
  ],
  "relations": [
    {{"subject": "object", "relation": "on|near|beside|inside|closed|visible", "object": "object_or_place"}}
  ],
  "states": [
    {{"entity": "object_or_agent", "attribute": "attribute_name", "value": "value"}}
  ],
  "affordances": [
    {{"object": "object_name", "actions": ["action_name"]}}
  ],
  "uncertainty": [
    {{"item": "object_or_state", "reason": "short reason", "level": "low|medium|high"}}
  ]
}}
"""
