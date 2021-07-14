"""
Custom logger to log using message templates based records to Elasticsearch through the CMRESHandler handler class.

    Usage:
        >> logger = init_logger(__name__, run_key="SwapPricing", extra={"route":"/api/swap_pricer/VanillaSwap"})
        >> logger.info("ParseInputs", LogStatus.Started)
        >> logger.error("ParseInputs", LogStatus.Error, "InvalidInputsException", "Failed to parse inputs")
"""

import os
import re
import logging
import logging.config
from logging import LogRecord, INFO

import yaml

from cmreslogging.handlers import CMRESHandler

__all__ = [
    "LogStatus", "init_logger", "LoggerWrapper", "configure_logger"
]

DEFAULT_CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "logging.yml")

DEFAULT_TEMPLATE_MESSAGE_INFO = '{runKey} {step} {status}'
DEFAULT_TEMPLATE_MESSAGE_ERROR = '{runKey} {step} {status} {exceptionType} {exceptionMessage}'
DEFAULT_TEMPLATE_MESSAGE_WARNING = '{runKey} {step} {detailedOrigin} {status}'
DEFAULT_TEMPLATE_MESSAGE_DEBUG = '{runKey} {step} {debugMessage}'


class LogStatus:
    Started = "Started"
    Ok = "Ok"
    Error = "Error"
    RanWithError = "RanWithError"
    Warning = "Warning"


class CustomAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra):
        super(CustomAdapter, self).__init__(logger, extra)
        self.logOrder = 0

    def info(self, msg, *args, **kwargs):
        """
        Delegate an info call to the underlying logger.
        """
        # noinspection PyArgumentList
        self.log(INFO, msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        """
        Delegate a log call to the underlying logger, after adding
        contextual information from this adapter instance.
        """

        if self.isEnabledFor(level):
            self.logOrder += 1
            msg, kwargs = self.process(msg, kwargs)
            extra = kwargs.pop("extra")
            if extra is not None:
                extra.update(dict(logOrder=self.logOrder))
            self.logger.log(level, msg, *args, **kwargs, extra=extra)


class MessageTemplateLogRecord(LogRecord):
    # noinspection PyArgumentList
    def __init__(self, name, level, pathname, lineno,
                 msg, args, exc_info, func=None, sinfo=None, **kwargs):
        super(MessageTemplateLogRecord, self).__init__(name, level, pathname, lineno, msg, args,
                                                       exc_info, func, sinfo, **kwargs)
        self.messageTemplate = None

    def getMessage(self):
        """
        Return the message for this LogRecord after merging any user-supplied
        arguments with the message.
        """
        msg = str(self.msg)
        if self.args:
            res = re.findall(r'{.*?}', msg)
            if not len(res):
                msg = self.msg % self.args
            else:
                self.messageTemplate = msg
                for i, word in enumerate(res):
                    self.__setattr__(word[1:-1], self.args[i])
                    msg = msg.replace(word, f"{ {i} }")

                msg = msg.format(*self.args)
        return msg


class LoggerWrapper:
    """
    Project specific logger adapter
    """
    _TEMPLATES = {
        "info": DEFAULT_TEMPLATE_MESSAGE_INFO,
        "error": DEFAULT_TEMPLATE_MESSAGE_ERROR,
        "warning": DEFAULT_TEMPLATE_MESSAGE_WARNING,
        "debug": DEFAULT_TEMPLATE_MESSAGE_DEBUG
    }

    def __init__(self, logger, run_key):
        self.runKey = run_key
        self.logger = logger

    def info(self, *args, **kwargs):
        self.logger.info(self._TEMPLATES['info'], self.runKey, *args, **kwargs)

    def error(self, *args, **kwargs):
        self.logger.error(self._TEMPLATES['error'], self.runKey, *args, **kwargs)

    def warn(self, *args, **kwargs):
        self.logger.warning(self._TEMPLATES['warning'], self.runKey, *args, **kwargs)

    def debug(self, *args, **kwargs):
        self.logger.debug(self._TEMPLATES['debug'], self.runKey, *args, **kwargs)

    @classmethod
    def register_template(cls, level, template_message):
        cls._TEMPLATES[level] = template_message


def configure_logger(es_config: dict, file_path: str = None):
    """
    Setup loggers to log the fit way
    :param es_config: dict object containing es configuration
    :param file_path: path to config file (.yaml)
    """
    if not file_path:
        file_path = DEFAULT_CONFIG_FILE_PATH

    try:
        with open(file_path, "rt") as f:
            log_config = yaml.safe_load(f.read())
            # noinspection PyArgumentList
            log_config["handlers"]['es_handler']['hosts'] = [{"host": es_config["host"], "port": es_config['port']}]
            log_config["handlers"]['es_handler']['auth_type'] = CMRESHandler.AuthType.BASIC_AUTH
            log_config["handlers"]['es_handler']['auth_details'] = es_config['token']
            log_config["handlers"]['es_handler']['es_index_name'] = es_config["index_name"]
            log_config["handlers"]['es_handler']["es_additional_fields"] = es_config['additional_fields']
            log_config["handlers"]['es_handler']['use_ssl'] = True
            log_config["handlers"]['es_handler']['verify_ssl'] = False
            logging.config.dictConfig(log_config)
            logging.setLogRecordFactory(MessageTemplateLogRecord)
    except Exception as e:
        print(e)
        print('Error in Logging Configuration. Using default config')
        logging.basicConfig(level=logging.DEBUG)


def init_logger(name: str, run_key: str = None, extra: dict = None):
    logger = logging.getLogger(name)
    adapter = LoggerWrapper(CustomAdapter(logger, extra=extra), run_key=run_key)
    return adapter