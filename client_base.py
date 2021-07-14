import time
import logging
import requests
import threading
import posixpath
from urllib.parse import urlsplit, urlunsplit

from datamodel import MISSING
from ezsgconnect import sgconnect

from .config import config, XOneEnv, ApiConfig

__all__ = [
    "raise_error", "XOneTradeInfoClient", "XOneCSAInfoClient", "XOnePricingModelClient",
    "HttpServerError", "ClientError", "Unauthorized", "NotFound", "check_response"
]


def is_ok(status):
    return 299 >= status >= 200


class HttpClientError(requests.HTTPError):
    pass


class HttpServerError(requests.HTTPError):
    pass


class Unauthorized(HttpClientError):
    pass


class NotFound(HttpClientError):
    pass


class ClientError(RuntimeError):
    pass


def check_response(resp: requests.Response) -> requests.Response:
    if not resp.ok:
        message = f'{resp.status_code}: {resp.text}'
        if not resp.text:
            try:
                resp.raise_for_status()
            except Exception as e:
                message = str(e)
        if resp.status_code == 403:
            raise Unauthorized(message)
        elif resp.status_code == 404:
            raise NotFound(message)
        else:
            raise ClientError(message)

    return resp


def raise_error(status, content):
    if is_ok(status):
        return

    if 499 >= status >= 400:
        raise HttpClientError(status, content)

    elif 599 >= status >= 500:
        raise HttpServerError(status, content)

    else:
        raise requests.HTTPError(status, content)


def get_logger():
    return logging.getLogger(__name__)


def url_join(url: str, *args) -> str:
    scheme, netloc, path, query, fragment = urlsplit(url)
    path = path if len(path) else "/"
    path = posixpath.join(path, *[('{}'.format(x)) for x in args])
    return urlunsplit([scheme, netloc, path, query, fragment])


class Client:
    _lock = threading.Lock()

    def __init__(self, api_name: str, *, env: XOneEnv, api: ApiConfig, loop=None):

        self._env = env
        self._api = api
        self._logger = get_logger()
        self._api_name = api_name
        self._requests_session = requests.Session()
        self._aiohttp_session = None
        self._loop = loop

    @property
    def env(self):
        return self._env

    @property
    def api(self):
        return self._api

    @property
    def logger(self):
        return self._logger

    def headers(self, is_mime : bool =False) -> dict:
        if not is_mime:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"}
        else:
            headers = {}

        if self._env.sgconnect_env is not MISSING:
            with self._lock:
                if self._api.token_mgr is MISSING:
                    self._logger.debug('Setting up token mgr ...')
                    if len(self._api.client_id) and len(self._api.client_secret):
                        self._logger.debug('Using client mode')
                        self._api.token_mgr = sgconnect(
                            client_id=self._api.client_id,
                            client_secret=self._api.client_secret,
                            server=self._env.sgconnect_env,
                            scope=self._api.scope)
                    else:
                        self._logger.debug('Using implicit mode')
                        self._api.token_mgr = sgconnect(
                            implicit_client_id=self._env.implicit_client_id,
                            implicit_redirect_uri=self._env.implicit_redirect_uri,
                            server=self._env.sgconnect_env,
                            scope=self._api.scope)
            token_value = self._api.token_mgr.get_token_value()
            headers["Authorization"] = 'Bearer ' + token_value

        else:
            self._logger.debug('No SGConnect required')

        if self._api.origin is not MISSING:
            self._logger.debug('Origin: %s', self._api.origin)
            headers["Origin"] = self._api.origin

        return headers


    def url(self, *last: str) -> str:
        return url_join(self._env.end_point, self._env.tessa_env, self._api_name, 'rest', *last)


    # noinspection PyShadowingNames
    def request(self, method: str, *last: str, json=None, stream=False, **params):
        url = self.url(*last)
        count = 0
        error = None
        timeout = config.timeout
        while count <= config.max_retries:
            try:
                is_mime = params.pop("is_mime") if "is_mime" in params else False
                resp = self._requests_session.request(
                    method, url, headers=self.headers(is_mime), json=json,
                    verify=False, stream=stream, timeout=timeout, **params)
                resp = check_response(resp)
            except Exception as exc:
                count += 1
                time.sleep(0.5 * count)
                timeout += count * 5
                error = exc
            else:
                return resp.json() if not stream else resp
        else:
            if error is not None:
                raise ClientError(f'Client request failed for {method.upper()} {url}: {error}')
            else:
                raise ClientError(f'Client request failed for {method.upper()} {url} without any exception')


    def get(self, *last: str, stream=False, **params):
        return self.request('get', *last, stream=stream, **params)


    def post(self, *last: str, data=None, **params):
        return self.request('post', *last, data=data, **params)


class XOneTradeInfoClient(Client):

    def __init__(self, env: XOneEnv):
        env = getattr(config.xone, env) if isinstance(env, str) else env
        super().__init__("TradeInformation", env=env, api=env.trade_information)

    def url(self, *last: str) -> str:
        return url_join(self._env.endpoint, 'api', self._api_name, self._env.version, *last)


class XOneCSAInfoClient(Client):

    def __init__(self, env: XOneEnv):
        env = getattr(config.xone, env) if isinstance(env, str) else env
        super().__init__("Csa", env=env, api=env.csa_information)

    def url(self, *last: str) -> str:
        return url_join(self._env.endpoint, 'api', self._api_name, "v1", *last)


class XOnePricingModelClient(Client):
    def __init__(self, env: XOneEnv):
        env = getattr(config.xone, env) if isinstance(env, str) else env
        super().__init__("Pim", env=env, api=env.pricing_model)

    def url(self, *last: str) -> str:
        return url_join(self._env.endpoint, 'api', self._api_name, "v1", "PricingInterfaceModel", *last)
