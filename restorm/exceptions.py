class RestException(Exception):
    pass


class ResourceException(RestException):
    pass


class RestServerException(RestException):
    pass


class DoesNotExist(RestException):
    pass
