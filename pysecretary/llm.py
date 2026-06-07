from typing import Any

from .config import SecretaryConfig
from .koboldcpp import KoboldCppClient


class LLMClient:
    def __init__(self, config: SecretaryConfig, api: KoboldCppClient | None = None) -> None:
        self.config = config
        self.api = api or KoboldCppClient.from_config(config)

    def _call_llm(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return self.api.chat_completion(
            messages=messages,
            model=self.config.llm_model,
            temperature=0.2,
        )

    def _extract_response_text(self, result: dict[str, Any]) -> str:
        if "choices" in result and result["choices"]:
            choice = result["choices"][0]
            message = choice.get("message", {})
            return (message.get("content") or "").strip()
        if "output" in result and result["output"]:
            output_item = result["output"][0]
            if isinstance(output_item, dict):
                return (output_item.get("content", "") or "").strip()
        return ""

    def clean_and_organize(self, raw_text: str) -> str:
        prompt = (
            "You are a secretary assistant. Clean up the following transcribed speech into "
            "a polished, logically organized set of paragraphs. Preserve meaning, fix grammar, and remove filler words. "
            "Do not include your internal thoughts in the final text."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": raw_text},
        ]
        result = self._call_llm(messages)
        return self._extract_response_text(result)

    def detect_task_request(self, cleaned_text: str) -> str:
        prompt = (
            "Review the cleaned passage and determine whether the speaker is asking the assistant to perform a follow-up task. "
            "If there is a concrete task request, reply only with the task description. If there is no task, reply with 'NONE'."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": cleaned_text},
        ]
        result = self._call_llm(messages)
        response = self._extract_response_text(result)
        if response.upper().strip() == "NONE":
            return ""
        return response

    def summarize_task_result(self, task_description: str, task_result: str) -> str:
        prompt = (
            "You are a secretary assistant. Summarize the task request and its result into a clear spoken response. "
            "Do not include internal reasoning in the spoken output."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Task: {task_description}\nResult: {task_result}"},
        ]
        result = self._call_llm(messages)
        return self._extract_response_text(result)
