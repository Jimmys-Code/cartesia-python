# This file was auto-generated by Fern from our API Definition.

from ...core.pydantic_utilities import UniversalBaseModel
from ...embedding.types.embedding import Embedding
from .localize_target_language import LocalizeTargetLanguage
from .gender import Gender
from .localize_dialect import LocalizeDialect
from ...core.pydantic_utilities import IS_PYDANTIC_V2
import typing
import pydantic


class LocalizeVoiceRequest(UniversalBaseModel):
    embedding: Embedding
    language: LocalizeTargetLanguage
    original_speaker_gender: Gender
    dialect: LocalizeDialect

    if IS_PYDANTIC_V2:
        model_config: typing.ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(extra="allow", frozen=True)  # type: ignore # Pydantic v2
    else:

        class Config:
            frozen = True
            smart_union = True
            extra = pydantic.Extra.allow
