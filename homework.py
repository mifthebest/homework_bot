import os
import time
import requests
import telegram
import logging
import sys

from dotenv import load_dotenv
from logging import StreamHandler
from exceptions import ErrStatusCode, ErrNonKey, ErrType, ErrEndpointRequest

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)
handler = StreamHandler(sys.stdout)
logger.addHandler(handler)

last_message = ''


def send_message(bot, message):
    """Отправка сообщений в чат пользователя"""

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f'Удачная отправка сообщения: {message}')
    except Exception:
        logger.error(f'Сбой при отправке сообщения: {message}')


def get_api_answer(current_timestamp):
    """Получение ответа от API  приведение его к типам данных Python"""

    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    headers = {
        'Authorization': f'OAuth {PRACTICUM_TOKEN}'
    }
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=headers,
            params=params
        )
    except Exception:
        logger.error('Сбой при запросе к эндпоинту')
        raise ErrEndpointRequest('Сбой при запросе к эндпоинту')
    else:
        if homework_statuses.status_code != 200:
            logger.error('Недоступность эндпоинта')
            raise ErrStatusCode(
                f'Ответ API олучен со статусом {homework_statuses.status_code}'
            )
        else:
            return homework_statuses.json()


def check_response(response):
    """Проверка корректности ответа API"""

    if type(response) is not dict:
        raise ErrType('Ответ API не приведён к типу dict')
    else:
        result = response.get('homeworks')
        if result is None:
            logger.error('Отсутствие ключа "homeworks" в ответе API')
            raise ErrNonKey('Отсутствие ключа "homeworks" в ответе API')
        elif type(result) is not list:
            raise ErrType(
                'Поле "homeworks" ответа API не приведёно к типу list'
            )
        else:
            return result


def parse_status(homework):
    """Парсинг ответа API и формирование сообщения для пользователя"""

    homework_name = homework.get('homework_name')
    if not homework_name:
        logger.error('Отсутствие ключа "homework_name" в ответе API')
        raise ErrNonKey('Отсутствие ключа "homework_name" в ответе API')

    homework_status = homework.get('status')
    if not homework_status:
        logger.error('Отсутствие ключа "homework_status" в ответе API')
        raise ErrNonKey('Отсутствие ключа "homework_status" в ответе API')

    verdict = HOMEWORK_STATUSES.get(homework_status)
    if not verdict:
        logger.error(
            'Недокументированный статус домашней работы, '
            'обнаруженный в ответе API'
        )
        raise ErrNonKey(
            'Недокументированный статус домашней работы, '
            'обнаруженный в ответе API'
        )

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка переменных среды"""

    return bool(PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)


def main():
    """Основная логика работы бота."""

    if not check_tokens():
        logger.critical('Отсутствие обязательных переменных окружения')
        exit(0)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = check_response(get_api_answer(current_timestamp))
            if not response:
                logger.debug('Отсутствие в ответе новых статусов')

            for homework in response:
                send_message(bot, parse_status(homework))

            current_timestamp = int(time.time())
            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'

            global last_message
            if message != last_message:
                send_message(bot, message)
                last_message = message
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
