class ArynSDKException(Exception):
    def __init__(self, raw_response):
        self.raw_response = raw_response

    @property
    def status_code(self):
        return self.raw_response.status_code

    def __str__(self):
        return f"ArynSDKException: status_code: {self.status_code}, raw_response: {self.raw_response}"
