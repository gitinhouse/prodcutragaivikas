from langgraph.graph import StateGraph, START, END
from chatbot.graph.state import GraphState

# Consolidated Super-Node Imports
from chatbot.graph.nodes.validator import validator_node
from chatbot.graph.nodes.controller import controller_node
from chatbot.graph.nodes.clarify import clarify_node 
from chatbot.graph.nodes.recommender import recommender_node 
from chatbot.graph.nodes.info_node import info_node
from chatbot.graph.nodes.fitment_node import fitment_node
from chatbot.graph.nodes.lead_evaluator import lead_evaluator_node
from chatbot.graph.nodes.synthesizer import synthesizer_node
from chatbot.graph.nodes.safety_guard import safety_guard_node

from chatbot.graph.edges import route_to_action


def create_sales_graph(checkpointer=None):
    """
    Sebastian 'Production 7' Architecture.
    Streamlined, High-Fidelity, Domain-Locked.
    """
    workflow = StateGraph(GraphState)

    # 1. Verification Level (Super-Node)
    workflow.add_node("Validator", validator_node)
    
    # 2. Strategic Level (Super-Node)
    workflow.add_node("Controller", controller_node)
    
    # 3. Action Level (Specialized Expert Branches)
    workflow.add_node("discovery_node", clarify_node)
    workflow.add_node("recommender_node", recommender_node)
    workflow.add_node("info_node", info_node)
    workflow.add_node("fitment_node", fitment_node)

    # 4. Evaluation & Synthesis Level
    workflow.add_node("Lead_evaluator", lead_evaluator_node)
    workflow.add_node("Synthesizer", synthesizer_node)
    workflow.add_node("SafetyGuard", safety_guard_node)
    
    # --- TOPOLOGY ---
    
    # Entry Chain
    workflow.add_edge(START, "Validator")
    workflow.add_edge("Validator", "Controller")
    
    # Action Routing (Deterministic Branches from Controller)
    workflow.add_conditional_edges(
        "Controller",
        route_to_action,
        {
            "recommender_node": "recommender_node",
            "info_node": "info_node",
            "discovery_node": "discovery_node",
            "fitment_node": "fitment_node",
            "hesitation_node": "info_node", # Merged hesitation into info for simplicity
            "lead_capture_node": "info_node", # Merged lead_capture entry into info
            "fallback_node": "discovery_node" # Merged fallback into discovery
        }
    )
    
    # Action Consolidation -> Lead Evaluator
    action_nodes = ["recommender_node", "info_node", "discovery_node", "fitment_node"]
    for node in action_nodes:
        workflow.add_edge(node, "Lead_evaluator")
        
    # Generation & Persistence
    workflow.add_edge("Lead_evaluator", "Synthesizer")
    workflow.add_edge("Synthesizer", "SafetyGuard")
    workflow.add_edge("SafetyGuard", END)

    return workflow.compile(checkpointer=checkpointer)
