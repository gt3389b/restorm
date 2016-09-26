class RestException(Exception):
    pass


class ResourceException(RestException):
    pass


class RestServerException(RestException):
    pass


class RestValidationException(RestException):
    def __init__(self, msg, response):
        self.response = response
        super(RestValidationException, self).__init__(msg)


class DoesNotExist(RestException):
    pass
