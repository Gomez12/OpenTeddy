"""
ETIM classification agent.

Focused agent that always looks up the correct ETIM class for a given product
term, strictly following the etim-lookup skill instructions.
"""

import sys
from baseagent import create_agent, run_agent

agent = create_agent(
    system_prompt=(
        "You are an ETIM classification specialist. Your sole purpose is to find the correct "
        "ETIM class code for a given product term.\n\n"
        "MANDATORY WORKFLOW:\n"
        "1. ALWAYS read the etim-lookup skill first (/skills/etim-lookup/SKILL.md)\n"
        "2. Follow ALL instructions in the skill — no shortcuts\n"
        "3. Perform the required minimum number of searches as specified in the skill\n"
        "4. Return the result in the exact JSON format specified in the skill\n\n"
        "You must NEVER skip the skill or take shortcuts. The skill defines the quality standard."
    ),
)

if __name__ == "__main__":
    product = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "LED lamp"
    query = f"Give me the best ETIM Class for {product}, if you are unsure then return me the options"
    sys.argv = [sys.argv[0], query]
    run_agent(agent, default_query=query)
