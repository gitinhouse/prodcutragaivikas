import json
import os
import asyncio
import logging
from typing import AsyncGenerator, Optional
from django.conf import settings
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from chatbot.graph.graph import create_sales_graph
from urllib.parse import quote_plus

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.services")

# --- SSE PERFORMANCE CONSTANTS ---
GRAPH_NODES = frozenset({
    "Validator", "Controller", "discovery_node", 
    "recommender_node", "info_node", "Lead_evaluator", 
    "Synthesizer"
})

class StreamService:
    """
    Core service to handle LangGraph streaming via SSE.
    Now instrumented for 100% Traceability.
    """
    
    _pool: Optional[AsyncConnectionPool] = None
    _checkpointer: Optional[AsyncPostgresSaver] = None
    _graph: Optional[object] = None 

    @classmethod
    async def get_checkpointer(cls) -> AsyncPostgresSaver:
        """Singleton pattern for checkpointer."""
        if cls._checkpointer is None:
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                from django.db import connections
                db_conn = connections['default'].settings_dict
                encoded_password = quote_plus(db_conn['PASSWORD'])

                db_url = f"postgres://{db_conn['USER']}:{encoded_password}@{db_conn['HOST']}:{db_conn['PORT']}/{db_conn['NAME']}"
                # db_url = f"postgres://{db_conn['USER']}:{db_conn['PASSWORD']}@{db_conn['HOST']}:{db_conn['PORT']}/{db_conn['NAME']}"

            pool_size = int(os.environ.get("DB_POOL_SIZE", 5))
            logger.info(f"DB Pool Init: Size={pool_size}")
            
            cls._pool = AsyncConnectionPool(conninfo=db_url, max_size=pool_size, kwargs={"autocommit": True})
            cls._checkpointer = AsyncPostgresSaver(cls._pool)
            await cls._checkpointer.setup()
            
        return cls._checkpointer

    @classmethod
    async def get_graph(cls):
        """Singleton pattern for compiled graph."""
        if cls._graph is None:
            checkpointer = await cls.get_checkpointer()
            cls._graph = create_sales_graph(checkpointer=checkpointer)
        return cls._graph

    @classmethod
    async def get_stream(cls, user_input: str, thread_id: str) -> AsyncGenerator[str, None]:
        """Runs LangGraph and yields SSE tokens."""
        logger.info(f"Starting Graph Execution Loop [Thread: {thread_id[:12]}]")
        
        from chatbot.models import AgentSession
        from asgiref.sync import sync_to_async
        
        try:
            # --- SYNCHRONIZATION LAYER (LOAD) ---
            session_obj, _ = await sync_to_async(AgentSession.objects.get_or_create)(
                session_id=thread_id,
                defaults={"sales_stage": AgentSession.Stage.DISCOVERY}
            )

            graph = await cls.get_graph()
            config = {"configurable": {"thread_id": thread_id}}
            initial_state = {
                "messages": [HumanMessage(content=user_input)],
                "session_id": session_obj.session_id,
                "sales_stage": session_obj.sales_stage,
                "vehicle_context": session_obj.vehicle_data,
                "sales_context": {
                    "budget_max": float(session_obj.identified_budget) if session_obj.identified_budget else None,
                    "style": session_obj.identified_style.get("style", None)
                },
                "identified_budget": float(session_obj.identified_budget) if session_obj.identified_budget else None,
                "identified_style": session_obj.identified_style
            }
            
            try:
                tokens_streamed = False
                total_tokens = 0
                import time
                start_time = time.time()
                
                async with asyncio.timeout(90.0):
                    async for event in graph.astream_events(initial_state, config, version="v2"):
                        kind = event["event"]
                        name = event["name"]
                        node = event["metadata"].get("langgraph_node") or event["metadata"].get("node") or "system"

                        # 1. TRACE: Node Transitions
                        if kind == "on_chain_start" and name in GRAPH_NODES:
                             logger.info(f"Node Transition: Starting {name}...")
                             yield f"data: {json.dumps({'type': 'thinking', 'content': f'Entering {name}...', 'node': name})}\n\n"

                        # 2. TRACE: Model Streams
                        if kind == "on_chat_model_stream":
                            if node == "Synthesizer":
                                content = event["data"]["chunk"].content
                                if content:
                                    tokens_streamed = True
                                    yield f"data: {json.dumps({'type': 'token', 'content': content, 'node': 'Synthesizer'})}\n\n"

                        # 3. TRACE: Token Accounting
                        if kind == "on_chat_model_end":
                            output = event["data"].get("output")
                            if output:
                                # Try modern usage_metadata first
                                usage = getattr(output, "usage_metadata", {})
                                if not usage:
                                    # Fallback to response_metadata
                                    usage = getattr(output, "response_metadata", {}).get("token_usage", {})
                                
                                if usage:
                                    total_tokens += usage.get("total_tokens", 0)

                        # 4. TRACE: Node Completion
                        if kind == "on_chain_end" and name in GRAPH_NODES:
                            logger.info(f"Node Transition: Completed {name}.")
                            if name == "Synthesizer" and not tokens_streamed:
                                output = event["data"].get("output", {})
                                messages = output.get("messages", [])
                                if messages:
                                    final_content = messages[-1].content
                                    if final_content:
                                        tokens_streamed = True
                                        yield f"data: {json.dumps({'type': 'token', 'content': final_content, 'node': 'Synthesizer'})}\n\n"

                # Calculate Final Metrics
                elapsed = round(time.time() - start_time, 2)
                yield f"data: {json.dumps({'type': 'metadata', 'time_seconds': elapsed, 'total_tokens': total_tokens})}\n\n"

            except asyncio.TimeoutError:
                logger.error(f"FATAL: Graph Timeout for thread {thread_id}")
                yield f"data: {json.dumps({'type': 'error', 'content': 'AI generation timed out'})}\n\n"
                return

            # --- SYNCHRONIZATION LAYER (SAVE) ---
            try:
                final_state = await graph.aget_state(config)
                state_values = final_state.values
                if state_values:
                    session_obj.sales_stage = state_values.get("sales_stage", session_obj.sales_stage)
                    session_obj.vehicle_data = state_values.get("vehicle_context", session_obj.vehicle_data)
                    
                    sales_context = state_values.get("sales_context", {})
                    if sales_context.get("budget_max"):
                        session_obj.identified_budget = sales_context.get("budget_max")
                    if sales_context.get("style"):
                        session_obj.identified_style["style"] = sales_context.get("style")
                        
                    # Legacy fallback
                    if not sales_context:
                        session_obj.identified_budget = state_values.get("identified_budget", session_obj.identified_budget)
                        session_obj.identified_style = state_values.get("identified_style", session_obj.identified_style)
                    
                    # --- LEAD SYNCHRONIZATION ---
                    from chatbot.models import Lead
                    email = state_values.get("customer_email")
                    name = state_values.get("customer_name")
                    if email:
                        lead_obj, _ = await sync_to_async(Lead.objects.get_or_create)(
                            email=email,
                            defaults={"first_name": name or "Valued Customer"}
                        )
                        # Update name if it was previously generic
                        if name and lead_obj.first_name == "Valued Customer":
                            lead_obj.first_name = name
                            await sync_to_async(lead_obj.save)()
                            
                        session_obj.lead = lead_obj

                    await sync_to_async(session_obj.save)()
                    logger.info(f"Session Sync Success: {session_obj.sales_stage}")
            except Exception as e:
                logger.error(f"Failed to sync AgentSession: {e}")

            logger.info(f"Graph Execution Success [Thread: {thread_id[:12]}]")
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"

        except Exception as e:
            logger.exception(f"FAULT in StreamService Loop")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
