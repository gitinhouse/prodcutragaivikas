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
                db_url = f"postgres://{db_conn['USER']}:{db_conn['PASSWORD']}@{db_conn['HOST']}:{db_conn['PORT']}/{db_conn['NAME']}"

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
        try:
            graph = await cls.get_graph()
            config = {"configurable": {"thread_id": thread_id}}
            initial_state = {"messages": [HumanMessage(content=user_input)]}
            
            try:
                tokens_streamed = False
                async with asyncio.timeout(30.0):
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

                        # 3. TRACE: Node Completion
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

            except asyncio.TimeoutError:
                logger.error(f"FATAL: Graph Timeout for thread {thread_id}")
                yield f"data: {json.dumps({'type': 'error', 'content': 'AI generation timed out'})}\n\n"
                return

            logger.info(f"Graph Execution Success [Thread: {thread_id[:12]}]")
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"

        except Exception as e:
            logger.exception(f"FAULT in StreamService Loop")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
