# This file was auto-generated by Fern from our API Definition.

from __future__ import annotations
import typing_extensions
import typing
from ..types.raw_encoding import RawEncoding


class OutputFormat_RawParams(typing_extensions.TypedDict):
    container: typing.Literal["raw"]
    encoding: RawEncoding
    sample_rate: int


class OutputFormat_WavParams(typing_extensions.TypedDict):
    container: typing.Literal["wav"]
    encoding: RawEncoding
    sample_rate: int


class OutputFormat_Mp3Params(typing_extensions.TypedDict):
    container: typing.Literal["mp3"]
    sample_rate: int
    bit_rate: int


OutputFormatParams = typing.Union[OutputFormat_RawParams, OutputFormat_WavParams, OutputFormat_Mp3Params]
