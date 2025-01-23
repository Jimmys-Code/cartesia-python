# This file was auto-generated by Fern from our API Definition.

from ...core.pydantic_utilities import UniversalBaseModel
import pydantic
from .tts_request_voice_specifier import TtsRequestVoiceSpecifier
import typing
from .supported_language import SupportedLanguage
from .web_socket_raw_output_format import WebSocketRawOutputFormat
from .context_id import ContextId
import typing_extensions
from ...core.serialization import FieldMetadata
from ...core.pydantic_utilities import IS_PYDANTIC_V2


class GenerationRequest(UniversalBaseModel):
    model_id: str = pydantic.Field()
    """
    The ID of the model to use for the generation. See [Models](/build-with-sonic/models) for available models.
    """

    transcript: str
    voice: TtsRequestVoiceSpecifier
    language: typing.Optional[SupportedLanguage] = None
    output_format: WebSocketRawOutputFormat
    duration: typing.Optional[float] = pydantic.Field(default=None)
    """
    The maximum duration of the audio in seconds. You do not usually need to specify this.
    If the duration is not appropriate for the length of the transcript, the output audio may be truncated.
    """

    context_id: ContextId
    continue_: typing_extensions.Annotated[typing.Optional[bool], FieldMetadata(alias="continue")] = pydantic.Field(
        default=None
    )
    """
    Whether this input may be followed by more inputs.
    If not specified, this defaults to `false`.
    """

    add_timestamps: typing.Optional[bool] = pydantic.Field(default=None)
    """
    Whether to return word-level timestamps.
    """

    add_phoneme_timestamps: typing.Optional[bool] = pydantic.Field(default=None)
    """
    Whether to return phoneme-level timestamps.
    """

    if IS_PYDANTIC_V2:
        model_config: typing.ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(extra="allow", frozen=True)  # type: ignore # Pydantic v2
    else:

        class Config:
            frozen = True
            smart_union = True
            extra = pydantic.Extra.allow
