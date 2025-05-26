"""
Executed once at app start‑up to (idempotently) register prompts.
"""

import logging
from langfuse import Langfuse
import os
from kvsecrets import prime_langfuse_env
prime_langfuse_env()
_LOGGER = logging.getLogger(__name__)
_langfuse = Langfuse(secret_key=os.getenv('LANGFUSE_SECRET_KEY'),
                     public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                     host=os.getenv('LANGFUSE_HOST'))


def _ensure_prompt(name: str, prompt: str, model=os.getenv('AZURE_DEPLOYMENT'), temperature=0.7):
    try: 
        _langfuse.get_prompt(name)
        _LOGGER.debug("Prompt %s already exists", name)
        return
    except Exception:
        pass
    _langfuse.create_prompt(
        name=name,
        prompt=prompt,
        config={"model": model, "temperature": temperature},
        labels=["production"],
    )
    _LOGGER.info("Prompt %s created", name)


def register_prompts_once():
    _ensure_prompt(
        "input-guardrail",
        """
        You are a guardrail checking the code and returning output in JSON format your role is not to optimize the codee rather check whether the given code can be optimize by other person or not.
    code: {{code}}
 
    Conditions:
    - you have to check whether or not there is any Sensitive information: No API keys or credentials. example (api_key="asafcsfx3adfa")
    - code must contain some code because if there is no code then how do you know what is it,
    - make sure user code is not just any random text (e.g., "jhcfkcjfandjbn121Chkhvajgv", "tree is falling").
    - code must not be only instructions (e.g., "how do i make pipeline in ML").
    - No random text (e.g., "jhcfkcjfandjbn121Chkhvajgv", "tree is falling").
    - if code contain some comments no problem it is good True.
    - do not check the syntax rather check if the given code is given to staff enginner can he complete it.
 
    Return a JSON object with a 'code' field (true if conditions are met, false otherwise) and an 'condition' field (short condition in 10 words of which condition If False).
    NOTE: Don't include any markdown formatting, code blocks, or explanations - just the raw JSON. make sure key name should be 'code' and 'condition'.
    
        """,
    )
    _ensure_prompt(
        "output-guardrail",
        """
        You are a code quality guardrail system.

        You will be given:
        1. An code snippet labeled as `optimized_code`
        2. A list of human feedback items labeled as `human_feedback_list`

        Your task:
        - For each feedback item in `human_feedback_list`, check whether it has been fully addressed in the `code`.
        - Identify which feedback items are incorporated correctly and which are missing or only partially implemented.
        - Your assessment must be accurate, concise, and directly tied to the content of the feedback and the code.
        - see the human_feedback_list from left to right there can be times where first human say to add stuff then say to remove stuff right side is most updated code and left side is the history 

        Return the output as a JSON object with two fields:
        - 'response': true if code contain all the things from human_feedback_list else false

        Input Format:
        code: {{optimized_code}}

        human_feedback_list: {{human_feedback_list}}

        NOTE: Don't include any markdown formatting, code blocks, or explanations - just the raw JSON.
    
        """,
    )
    _ensure_prompt(
        "optimize-code",
        """
          You are an expert code optimizer.

        Your task:
        - Carefully read and understand code. Use it to guide your optimization.
        - Performance
        - Readability
        - Maintainability
        - Best coding practices
        - Add comments and docstrings to the code.

        Return the output as a JSON object with code with field 'code'.
        Don't include any markdown formatting, code blocks, or explanations - just the raw JSON.

        Input Format:
        code: {{user_input}}

        NOTE: Don't include any markdown formatting, code blocks, or explanations - just the raw JSON.  return Code only in key 'code'.

        """,
    )
