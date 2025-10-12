from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types
from typing import Optional
from detoxify import Detoxify
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine, OperatorConfig


def topic_classify(prompt: str) -> str:
    """
    Classify the user prompt into categories such as:
    - “medical”
    - “companionship”
    - “administrative”
    - “out_of_scope”
    - etc.
    
    This is a simple rule-based / keyword-based fallback; in practice you might
    use a trained classifier (fine-tuned transformer) for improved accuracy.
    """
    text = prompt.lower()
    # crude keyword-based heuristics
    medical_keywords = ["pain", "symptom", "diagnose", "medicine", "treatment", "dose", "doctor"]
    admin_keywords = ["appointment", "schedule", "billing", "insurance", "hours", "visit"]
    companion_keywords = ["how are you", "feel", "talk", "music", "joke", "story"]
    
    for kw in medical_keywords:
        if kw in text:
            return "medical"
    for kw in admin_keywords:
        if kw in text:
            return "administrative"
    for kw in companion_keywords:
        if kw in text:
            return "companionship"
    # If it contains something clearly out-of-scope
    out_of_scope_markers = ["stock", "invest", "loan", "politics", "religion", "legal advice"]
    for kw in out_of_scope_markers:
        if kw in text:
            return "out_of_scope"
    # fallback
    return "general"


# ========== PII Redaction ==========

# Initialize Presidio engines (shared globally to avoid repeated instantiation)
_analyzer = AnalyzerEngine()
_anonymizer = AnonymizerEngine()

def pii_redact(text: str) -> str:
    """
    Detect and redact PII in the input text using Presidio.
    Returns a text where detected PII spans are replaced (e.g. with “[REDACTED]”).
    """
    # Analyze for PII entities
    results = _analyzer.analyze(text=text, entities=None, language="en")
    if not results:
        return text
    
    # Configure anonymization: replace everything with “[REDACTED]”
    operators = {
        ent.entity_type: OperatorConfig("replace", {"new_value": "[REDACTED]"}) 
        for ent in results
    }
    
    redacted = _anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operator_config=operators
    ).text
    return redacted


# ========== Harmful / Toxicity checking ==========

_detox_model = Detoxify('original')  # load the detoxify model

def is_harmful(text: str, threshold: float = 0.5) -> Tuple[bool, Optional[str]]:
    """
    Return (True, reason) if text is harmful / toxic; else (False, None).
    Uses Detoxify to estimate toxicity across categories.
    
    threshold: a cutoff probability above which we consider it harmful.
    """
    # Get scores from detoxify
    scores = _detox_model.predict(text)
    # scores is a dict, e.g. {"toxicity": 0.02, "insult": 0.001, ...} :contentReference[oaicite:3]{index=3}
    # We choose “toxicity” as the main measure
    tox_score = scores.get("toxicity", 0.0)
    if tox_score >= threshold:
        # Optionally pick which label triggered
        # Find highest scoring label
        highest = max(scores.items(), key=lambda kv: kv[1])
        return True, f"{highest[0]} = {highest[1]:.3f}"
    return False, None

SAFE_FALLBACK = "I’m sorry, I can’t help with that request, but I can notify a nurse or direct you to medical staff."

def before_model_guardrails(
    callback_context: CallbackContext,
    llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Intercepts user input / prompt before sending to the LLM."""
    agent_name = callback_context.agent_name
    # Combine all user parts into a single prompt string
    user_text = ""
    for c in llm_request.contents:
        if c.role == "user":
            for p in c.parts:
                user_text += p.text or ""
    # --- Topic check ---
    topic = topic_classify(user_text)
    if topic == "out_of_scope":
        # Return a safe canned response (skip the LLM call)
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=SAFE_FALLBACK)]
            )
        )
    # --- PII redaction on user input ---
    redacted_text = pii_redact(user_text)
    # Replace the user content in llm_request with redacted version
    for c in llm_request.contents:
        if c.role == "user":
            for idx, p in enumerate(c.parts):
                # Simplest: replace entire text. You could preserve structure.
                c.parts[idx].text = redacted_text


    # Allow the LLM call to proceed
    return None


def after_model_guardrails(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
    llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """Intercepts the model’s output and validate before returning to user."""
    agent_name = callback_context.agent_name
    # Combine the text of the model response
    resp_text = ""
    for part in llm_response.content.parts:
        resp_text += part.text or ""
    # --- Harmful / toxicity / bias check ---
    harmful, reason = is_harmful(resp_text)
    if harmful:
        # Replace with safe fallback or regenerate
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=SAFE_FALLBACK)]
            )
        )
    
    # --- PII redaction in output ---
    redacted_resp = pii_redact(resp_text)
    # Replace the content parts
    new_content = types.Content(role="model", parts=[types.Part(text=redacted_resp)])
    return LlmResponse(content=new_content)

