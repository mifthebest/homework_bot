import os
import sys
import time

import requests
import telegram

from dotenv import load_dotenv

import logging

from logging import StreamHandler
from logging.handlers import RotatingFileHandler

from exceptions import StatusCodeError, ServerError


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
)
stream_handler = StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
LOGGER.addHandler(stream_handler)
file_handler = RotatingFileHandler(
    'logger.log',
    maxBytes=50000000,
    backupCount=25
)
file_handler.setFormatter(formatter)
LOGGER.addHandler(file_handler)


ERROR_MESSAGE = 'Сбой в работе программы: {error}'
ERROR_STATUS_CODE_MESSAGE = (
    'Ответ API получен со статусом {status_code}, args: '
    'endpoint = {endpoint}, headers = {headers}, params = {params}'
)
ERROR_REQUEST_TO_ENDPOINT_MESSAGE = (
    'Сбой при запросе к эндпоинту, args: '
    'endpoint = {endpoint}, headers = {headers}, params = {params}.'
    'Текст перехваченного исключения: {error}'
)
ERROR_SERVER_MESSAGE = (
    'Ошибка на сервере, args: '
    'endpoint = {endpoint}, headers = {headers}, params = {params}.'
    'Текст поля error: {error}. Текст поля code: {code}'
)
ERROR_NOT_DOCUMENTED_STATUS_MESSAGE = (
    'Недокументированный статус {homework_status} '
    'домашней работы {homework_name}, обнаруженный в ответе API'
)
ERROR_NOT_DICT_TYPE_MESSAGE = 'Ответ API не приведён к типу dict'
ERROR_NOT_LIST_TYPE_MESSAGE = (
    'Поле "homeworks" ответа API не приведёно к типу list'
)
ERROR_SENDING_TEXT_MESSAGE = (
    'Ошибка при отправке сообщения, args: '
    'chat_id = {TELEGRAM_CHAT_ID}, message = {message}'
    'Текст перехваченного исключения: {error}'
)

INFO_SENDING_TEXT_MESSAGE = 'Удачная отправка сообщения: {message}'

DEBUG_HAVE_NOT_NEW_STATUSES_MESSAGE = 'Отсутствуют новые статусы в ответе API'

CRITICAL_HAVE_NOT_ENV_VAR_MESSAGE = (
    'Отсутствуют обязательные переменные окружения'
)


def send_message(bot, message):
    """Отправка сообщений в чат пользователя."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        LOGGER.info(INFO_SENDING_TEXT_MESSAGE.format(message=message))
    except telegram.error.TelegramError as error:
        LOGGER.error(
            ERROR_SENDING_TEXT_MESSAGE.format(
                chat_id={TELEGRAM_CHAT_ID},
                message={message},
                error=error
            )
        )
        return ''
    return message


def get_api_answer(current_timestamp):
    """Получение ответа от API  приведение его к типам данных Python."""
    params = {'from_date': current_timestamp}

    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except requests.RequestException as error:
        raise requests.RequestException(
            ERROR_REQUEST_TO_ENDPOINT_MESSAGE.format(
                endpoint=ENDPOINT,
                headers=HEADERS,
                params=params,
                error=error
            )
        )

    if homework_statuses.status_code != 200:
        raise StatusCodeError(
            ERROR_STATUS_CODE_MESSAGE.format(
                status_code=homework_statuses.status_code,
                endpoint=ENDPOINT,
                headers=HEADERS,
                params=params
            )
        )

    result = homework_statuses.json()
    if 'error' in result or 'code' in result:
        raise ServerError(
            ERROR_SERVER_MESSAGE.format(
                endpoint=ENDPOINT,
                headers=HEADERS,
                params=params,
                error=result.get('error'),
                code=result.get('code')
            )
        )

    return result


def check_response(response):
    """Проверка корректности ответа API."""
    if type(response) is not dict:
        raise TypeError(ERROR_NOT_DICT_TYPE_MESSAGE)

    result = response['homeworks']

    if type(result) is not list:
        raise TypeError(ERROR_NOT_LIST_TYPE_MESSAGE)

    return result


def parse_status(homework):
    """Парсинг ответа API и формирование сообщения для пользователя."""
    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        raise(
            ValueError(
                ERROR_NOT_DOCUMENTED_STATUS_MESSAGE.format(
                    homework_status=homework_status,
                    homework_name=homework_name
                )
            )
        )
    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка переменных среды."""
    return bool(PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_message = ''

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if not homeworks:
                LOGGER.debug(DEBUG_HAVE_NOT_NEW_STATUSES_MESSAGE)
            else:
                send_message(bot, parse_status(homeworks[0]))

            current_timestamp = response['current_date']

        except Exception as error:
            message = ERROR_MESSAGE.format(error=error)
            LOGGER.error(error)

            if message != last_message or last_message == '':
                last_message = send_message(bot, message)

        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    if check_tokens():
        main()
    else:
        LOGGER.critical(CRITICAL_HAVE_NOT_ENV_VAR_MESSAGE)
        exit(0)
