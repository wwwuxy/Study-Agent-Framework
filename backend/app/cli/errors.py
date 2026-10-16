class CLIError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 1):
        self.code, self.message, self.exit_code = code, message, exit_code
        super().__init__(message)
