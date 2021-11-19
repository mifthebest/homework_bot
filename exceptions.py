class StatusCodeError(Exception):
    """Код возврата API отличен от 200"""
    pass


class ServerError(Exception):
    """Ошибка на сервере"""
    pass
