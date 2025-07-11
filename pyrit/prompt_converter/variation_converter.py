# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import json
import logging
import pathlib
import uuid
from textwrap import dedent

from pyrit.common.path import DATASETS_PATH
from pyrit.exceptions import (
    InvalidJsonException,
    pyrit_json_retry,
    remove_markdown_json,
)
from pyrit.models import (
    PromptDataType,
    PromptRequestPiece,
    PromptRequestResponse,
    SeedPrompt,
)
from pyrit.prompt_converter import ConverterResult, PromptConverter
from pyrit.prompt_target import PromptChatTarget

logger = logging.getLogger(__name__)


class VariationConverter(PromptConverter):
    """
    Generates variations of the input prompts using the converter target.
    """

    def __init__(self, *, converter_target: PromptChatTarget, prompt_template: SeedPrompt = None):
        """
        Initializes the converter with the specified target and prompt template.

        Args:
            converter_target (PromptChatTarget): The target to which the prompt will be sent for conversion.
            prompt_template (SeedPrompt, optional): The template used for generating the system prompt.
                If not provided, a default template will be used.
        """
        self.converter_target = converter_target

        # set to default strategy if not provided
        prompt_template = (
            prompt_template
            if prompt_template
            else SeedPrompt.from_yaml_file(
                pathlib.Path(DATASETS_PATH) / "prompt_converters" / "variation_converter.yaml"
            )
        )

        self.number_variations = 1

        self.system_prompt = str(prompt_template.render_template_value(number_iterations=str(self.number_variations)))

    async def convert_async(self, *, prompt: str, input_type: PromptDataType = "text") -> ConverterResult:
        """
        Converts the given prompt by generating variations of it using the converter target.

        Args:
            prompt (str): The prompt to be converted.

        Returns:
            ConverterResult: The result containing the generated variations.

        Raises:
            ValueError: If the input type is not supported.
        """
        if not self.input_supported(input_type):
            raise ValueError("Input type not supported")

        conversation_id = str(uuid.uuid4())

        self.converter_target.set_system_prompt(
            system_prompt=self.system_prompt,
            conversation_id=conversation_id,
            orchestrator_identifier=None,
        )

        prompt = dedent(
            f"Create {self.number_variations} variation of the seed prompt given by the user between the "
            "begin and end tags"
            "=== begin ==="
            f"{prompt}"
            "=== end ==="
        )

        request = PromptRequestResponse(
            [
                PromptRequestPiece(
                    role="user",
                    original_value=prompt,
                    converted_value=prompt,
                    conversation_id=conversation_id,
                    sequence=1,
                    prompt_target_identifier=self.converter_target.get_identifier(),
                    original_value_data_type=input_type,
                    converted_value_data_type=input_type,
                    converter_identifiers=[self.get_identifier()],
                )
            ]
        )
        response_msg = await self.send_variation_prompt_async(request)

        return ConverterResult(output_text=response_msg, output_type="text")

    @pyrit_json_retry
    async def send_variation_prompt_async(self, request):
        """Sends the prompt request to the converter target and retrieves the response."""
        response = await self.converter_target.send_prompt_async(prompt_request=request)

        response_msg = response.get_value()
        response_msg = remove_markdown_json(response_msg)
        try:
            response = json.loads(response_msg)

        except json.JSONDecodeError:
            raise InvalidJsonException(message=f"Invalid JSON response: {response_msg}")

        try:
            return response[0]
        except KeyError:
            raise InvalidJsonException(message=f"Invalid JSON response: {response_msg}")

    def input_supported(self, input_type: PromptDataType) -> bool:
        return input_type == "text"

    def output_supported(self, output_type: PromptDataType) -> bool:
        return output_type == "text"
