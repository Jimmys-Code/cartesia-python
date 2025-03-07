# This file was auto-generated by Fern from our API Definition.

import typing_extensions
from ...embedding.types.embedding import Embedding
from ..types.localize_target_language import LocalizeTargetLanguage
from ..types.gender import Gender
import typing_extensions
from .localize_dialect import LocalizeDialectParams


class LocalizeVoiceRequestParams(typing_extensions.TypedDict):
    embedding: Embedding
    language: LocalizeTargetLanguage
    original_speaker_gender: Gender
    dialect: typing_extensions.NotRequired[LocalizeDialectParams]
