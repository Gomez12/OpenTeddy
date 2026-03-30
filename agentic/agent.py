"""
General-purpose OpenTeddy agent.

A versatile assistant that can classify products (ETIM), execute code,
browse the web, and create documents — all using the shared base agent.
"""

from baseagent import create_agent, run_agent

agent = create_agent(
    system_prompt=(
        "You are a helpful assistant that specialises in ETIM product classification.\n"
        "For ETIM classification: ALWAYS read and follow the etim-lookup skill before using search tools.\n"
        "The skill contains the required search strategy (minimum number of searches, output format, etc.).\n\n"
        "CRITICAL OUTPUT RULE:\n"
        "When returning ETIM classification results, you MUST return ONLY valid JSON — no markdown,\n"
        "no tables, no prose, no headers. The JSON format is defined in the etim-lookup skill.\n"
        "Every filled feature MUST include value_confidence and value_source fields.\n"
        "If the product came from a URL, include source_url in the JSON.\n"
    ),
)

if __name__ == "__main__":
    run_agent(agent, default_query="Classificeer een stopcontact met randaarde")
