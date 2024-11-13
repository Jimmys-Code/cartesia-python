# This file was auto-generated by Fern from our API Definition.

import typing

import httpx

from .environment import CartesiaEnvironment
from .base_client import AsyncBaseCartesia, BaseCartesia
from .tts.socket_client import AsyncTtsClientWithWebsocket, TtsClientWithWebsocket


class Cartesia(BaseCartesia):
    """
    Use this class to access the different functions within the SDK. You can instantiate any number of clients with different configuration that will propagate to these functions.

    Parameters
    ----------
    base_url : typing.Optional[str]
        The base url to use for requests from the client.

    environment : CartesiaEnvironment
        The environment to use for requests from the client. from .environment import CartesiaEnvironment



        Defaults to CartesiaEnvironment.PRODUCTION



    api_key_header : str
    timeout : typing.Optional[float]
        The timeout to be used, in seconds, for requests. By default the timeout is 60 seconds, unless a custom httpx client is used, in which case this default is not enforced.

    follow_redirects : typing.Optional[bool]
        Whether the default httpx client follows redirects or not, this is irrelevant if a custom httpx client is passed in.

    httpx_client : typing.Optional[httpx.Client]
        The httpx client to use for making requests, a preconfigured client is used by default, however this is useful should you want to pass in any custom httpx configuration.

    Examples
    --------
    from cartesia import Cartesia

    client = Cartesia(
        api_key_header="YOUR_API_KEY_HEADER",
    )
    """

    def __init__(
        self,
        *,
        base_url: typing.Optional[str] = None,
        environment: CartesiaEnvironment = CartesiaEnvironment.PRODUCTION,
        api_key_header: str,
        timeout: typing.Optional[float] = None,
        follow_redirects: typing.Optional[bool] = True,
        httpx_client: typing.Optional[httpx.Client] = None,
    ):
        super().__init__(
            base_url=base_url,
            environment=environment,
            api_key_header=api_key_header,
            timeout=timeout,
            follow_redirects=follow_redirects,
            httpx_client=httpx_client,
        )
        self.tts = TtsClientWithWebsocket(client_wrapper=self._client_wrapper)


class AsyncCartesia(AsyncBaseCartesia):
    """
    Use this class to access the different functions within the SDK. You can instantiate any number of clients with different configuration that will propagate to these functions.

    Parameters
    ----------
    base_url : typing.Optional[str]
        The base url to use for requests from the client.

    environment : CartesiaEnvironment
        The environment to use for requests from the client. from .environment import CartesiaEnvironment



        Defaults to CartesiaEnvironment.PRODUCTION



    api_key_header : str
    timeout : typing.Optional[float]
        The timeout to be used, in seconds, for requests. By default the timeout is 60 seconds, unless a custom httpx client is used, in which case this default is not enforced.

    follow_redirects : typing.Optional[bool]
        Whether the default httpx client follows redirects or not, this is irrelevant if a custom httpx client is passed in.

    httpx_client : typing.Optional[httpx.AsyncClient]
        The httpx client to use for making requests, a preconfigured client is used by default, however this is useful should you want to pass in any custom httpx configuration.

    Examples
    --------
    from cartesia import AsyncCartesia

    client = AsyncCartesia(
        api_key_header="YOUR_API_KEY_HEADER",
    )
    """

    def __init__(
        self,
        *,
        base_url: typing.Optional[str] = None,
        environment: CartesiaEnvironment = CartesiaEnvironment.PRODUCTION,
        api_key_header: str,
        timeout: typing.Optional[float] = None,
        follow_redirects: typing.Optional[bool] = True,
        httpx_client: typing.Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(
            base_url=base_url,
            environment=environment,
            api_key_header=api_key_header,
            timeout=timeout,
            follow_redirects=follow_redirects,
            httpx_client=httpx_client,
        )
        self.tts = AsyncTtsClientWithWebsocket(client_wrapper=self._client_wrapper)
