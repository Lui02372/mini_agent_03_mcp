"""Adapted from 07_multi-agent-service-ops/shared/travel_llm.py.

Same structured output contract for OpenAI Responses, Gemini and Ollama chat.
Provider failures are not presented as successful real model calls.
"""
import asyncio
import os
import httpx
from openai import AsyncOpenAI
from .multi_models import AgentAnswer


def model_name(provider):
    return {'openai': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
            'gemini': os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite'),
            'gemma': os.getenv('GEMMA_MODEL', 'gemma3:1b'),
            'ollama': os.getenv('OLLAMA_MODEL', 'qwen3:1.7b'), 'mock': 'deterministic-demo'}[provider]


async def structured(provider: str, prompt: str) -> AgentAnswer:
    async with asyncio.timeout(300 if provider in ('ollama', 'gemma') else 35):
        if provider == 'openai':
            if not os.getenv('OPENAI_API_KEY'):
                raise ValueError('missing key')
            async with AsyncOpenAI(timeout=30, max_retries=0) as client:
                result = await client.responses.parse(model=model_name(provider), input=prompt,
                                                      text_format=AgentAnswer, max_output_tokens=1200)
                if result.output_parsed is None:
                    raise ValueError('no structured answer')
                return result.output_parsed
        if provider == 'gemini':
            if not os.getenv('GEMINI_API_KEY'):
                raise ValueError('missing key')
            from google import genai
            async with genai.Client(api_key=os.environ['GEMINI_API_KEY'],
                                    http_options={'timeout': 30000}).aio as client:
                result = await client.models.generate_content(
                    model=model_name(provider), contents=prompt,
                    config={'response_mime_type': 'application/json',
                            'response_json_schema': AgentAnswer.model_json_schema(),
                            'max_output_tokens': 2048, 'temperature': 0, 'automatic_function_calling': {'disable': True}})
                return AgentAnswer.model_validate_json(result.text or '')
        if provider in ('ollama', 'gemma'):
            async with httpx.AsyncClient(timeout=290) as client:
                response = await client.post(os.getenv('OLLAMA_BASE_URL', 'http://host.docker.internal:11434').rstrip('/') + '/api/chat',
                    json={'model': model_name(provider), 'stream': False,
                          **({'think': False} if provider == 'ollama' else {}),
                          'options': {'num_ctx': 3072, 'num_predict': 450, 'temperature': 0.1, 'num_thread': 2},
                          'messages': [{'role': 'user', 'content': prompt}],
                          'format': AgentAnswer.model_json_schema()})
                response.raise_for_status()
                return AgentAnswer.model_validate_json(response.json()['message']['content'])
        raise ValueError('unsupported real provider')
