import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

logger = logging.getLogger(__name__)

class LLMSettings(BaseSettings):
    """
    LLM Configuration using Pydantic Settings for environment safety.
    """
    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: Optional[str] = None
    DEFAULT_MODEL: str
    EMBEDDING_MODEL: str
    TEMPERATURE: float
    MAX_ITERATIONS: int
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"
    )

# Singletons (Lazy Initialized)
_llm_instance: Optional[ChatOpenAI] = None
_embedding_instance: Optional[OpenAIEmbeddings] = None

def get_llm() -> ChatOpenAI:
    """
    Returns the singleton ChatOpenAI client with Lazy Loading.
    Ensures the app doesn't crash during build/migration if key is missing.
    """
    global _llm_instance
    if _llm_instance is None:
        try:
            settings = LLMSettings()
            _llm_instance = ChatOpenAI(
                openai_api_key=settings.OPENAI_API_KEY,
                model=settings.DEFAULT_MODEL,
                temperature=settings.TEMPERATURE
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChatOpenAI: {str(e)}")
            # Fallback for non-critical paths or informative error
            raise RuntimeError("LLM Configuration missing or invalid (OPENAI_API_KEY). Check your .env file.")
    return _llm_instance

def get_embeddings() -> OpenAIEmbeddings:
    """
    Returns the singleton OpenAIEmbeddings client with Lazy Loading.
    """
    global _embedding_instance
    if _embedding_instance is None:
        try:
            settings = LLMSettings()
            _embedding_instance = OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY,
                model=settings.EMBEDDING_MODEL
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAIEmbeddings: {str(e)}")
            raise RuntimeError("Embedding Configuration missing or invalid. Check your .env file.")
    return _embedding_instance
