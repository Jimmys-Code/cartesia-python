# This file was auto-generated by Fern from our API Definition.

from ...core.pydantic_utilities import UniversalBaseModel
import pydantic
from .output_format import OutputFormat
import typing
from .tts_request_voice_specifier import TtsRequestVoiceSpecifier
from ...core.pydantic_utilities import IS_PYDANTIC_V2


class WebSocketTtsRequest(UniversalBaseModel):
    model_id: str = pydantic.Field()
    """
    The ID of the model to use for the generation. See [Models](/build-with-sonic/models) for available models.
    """

    output_format: OutputFormat
    transcript: typing.Optional[str] = None
    voice: TtsRequestVoiceSpecifier
    duration: typing.Optional[int] = None
    language: typing.Optional[str] = None
    add_timestamps: bool
    context_id: typing.Optional[str] = None

    if IS_PYDANTIC_V2:
        model_config: typing.ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(extra="allow", frozen=True)  # type: ignore # Pydantic v2
    else:

        class Config:
            frozen = True
            smart_union = True
            extra = pydantic.Extra.allow
