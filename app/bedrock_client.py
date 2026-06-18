import os
from typing import Any


class BedrockResult:
    def __init__(self, text: str | None, error: str | None = None) -> None:
        self.text = text
        self.error = error


class BedrockAdvisor:
    def __init__(self) -> None:
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "")
        self.enabled = os.getenv("USE_BEDROCK", "false").lower() == "true" and bool(self.model_id)
        self.last_error: str | None = None

    def generate(self, system_prompt: str, user_prompt: str, context: dict[str, Any]) -> BedrockResult:
        self.last_error = None
        if not self.enabled:
            return BedrockResult(None)

        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            self.last_error = "boto3 is not installed"
            return BedrockResult(None, self.last_error)

        try:
            client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                config=Config(
                    connect_timeout=5,
                    read_timeout=20,
                    retries={"max_attempts": 1, "mode": "standard"},
                ),
            )
            response = client.converse(
                modelId=self.model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "Use only this approved AWS service-pack context. "
                                    "Do not invent services, metrics, IAM actions, or controls.\n\n"
                                    f"Context:\n{context}\n\n"
                                    f"User question:\n{user_prompt}"
                                )
                            }
                        ],
                    }
                ],
                inferenceConfig={"temperature": 0.2, "maxTokens": 1400},
            )
            return BedrockResult(response["output"]["message"]["content"][0]["text"])
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {str(error)}"
            return BedrockResult(None, self.last_error)

    def status(self) -> dict[str, str | bool | None]:
        return {
            "enabled": self.enabled,
            "model_id": self.model_id or None,
            "region": self.region,
            "last_error": self.last_error,
        }
