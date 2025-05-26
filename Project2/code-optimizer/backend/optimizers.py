"""
Composite optimisation chain:
    (input guardrail) ➜ optimise ➜ (output guardrail)

Retries the inner optimise+output_guardrail up to MAX_RETRIES.
"""

import logging
from typing import List
from utils import _llm, _prompt
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from langfuse.callback import CallbackHandler
import os

from guardrails import input_guardrail, output_guardrail
_LOGGER = logging.getLogger(__name__)
MAX_RETRIES = 3


# ───────────────── optimise prompt parser ──────────────────
class _OptimizeResp(BaseModel):
    code: str = Field(description="Optimised code")


def _optimize_once(code: str) -> str:
    p = _prompt("optimize-code")
    parser = JsonOutputParser(pydantic_object=_OptimizeResp)

    chain = (
        PromptTemplate(
            template=p.prompt,
            input_variables=p.variables,
            partial_variables={"format_instructions": parser.get_format_instructions()},
            template_format='mustache'
        )
        | _llm(p.config["model"], float(p.config["temperature"]))
        | parser
    )

    return chain.invoke(
        {"user_input": code}, config={"callbacks": [CallbackHandler(host=os.getenv("LANGFUSE_HOST"))]}
    )['code']


def optimise_with_guardrails(code: str, feedback_history: List[str]) -> str:
    ok, reason = input_guardrail(code)
    if not ok:
        raise ValueError(f"Input guardrail failed: {reason}")

    for attempt in range(1, MAX_RETRIES + 1):
        optimised = _optimize_once(code)
        if output_guardrail(optimised, feedback_history):
            _LOGGER.info("Output guardrail passed on try %s", attempt)
            return optimised
        _LOGGER.warning("Output guardrail failed on try %s", attempt)

    raise RuntimeError("Failed to satisfy output guardrail after retries")