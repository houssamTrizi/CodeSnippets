"""
Note about the datamodel library: datamodel is an internal library build on top of the dataclass library,
                    to add auto-mapping from python types and JSON.

Rationale: we constantly struggle to manage the mapping from/to dict object (json, etc..) and with a lack of proper
           model classes and type definition makes the code difficult to read/check and maintain, using python 3.6+
           type annotations and typing library and the 3.7 dataclass library we define a datamodel class decorator to
           help on this mapping.
"""


import json
import os
import typing

from datamodel import datamodel, optional, required

__all__ = ['config', 'ApiConfig', 'XOneEnv', 'EnvType']


@datamodel
class ApiConfig:
    comment: str = optional()
    origin: str = optional()

    scope: str
    client_id: str = optional(default="")
    client_secret: str = optional(default="")

    token_mgr: typing.Any = optional()


@datamodel
class XOneEnv:
    trade_information: ApiConfig
    csa_information: ApiConfig
    pricing_model: ApiConfig

    endpoint: str = required()
    xone_env: str = required()

    version: str = required()

    sgconnect_env: str = optional(default="dev")

    implicit_client_id: str = optional(default="")
    implicit_redirect_uri: str = optional(default="")


@datamodel
class XOneConfig:
    prod: XOneEnv
    uat: XOneEnv
    prebeta: XOneEnv
    yesterday: XOneEnv


@datamodel
class RootConfig:
    xone: XOneConfig

    logger: str = optional(default='fit_xone')
    max_retries: int = optional(default=0)
    timeout: int = optional(default=60)


def load_config() -> RootConfig:
    json_file = 'config.json'
    home_settings = os.path.join(os.path.expanduser('~'), '.fit_xone', json_file)
    config_path = os.environ.get('PYTHON_XONE_CONFIG', home_settings)

    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), json_file)
    with open(config_path, 'rt') as fp:
        return RootConfig.build(json.load(fp))


EnvType = typing.Union[str, XOneEnv]

config = load_config()