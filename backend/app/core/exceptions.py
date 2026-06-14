"""全局自定义异常与统一异常处理器。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """业务异常基类，携带 HTTP 状态码与错误信息。"""

    def __init__(self, status_code: int, message: str, code: int = -1):
        self.status_code = status_code
        self.message = message
        self.code = code


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(404, message)


class ForbiddenException(AppException):
    def __init__(self, message: str = "无权限访问"):
        super().__init__(403, message)


class BadRequestException(AppException):
    def __init__(self, message: str = "请求参数错误"):
        super().__init__(400, message)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "未登录或令牌失效"):
        super().__init__(401, message)


class QuotaExceededException(AppException):
    def __init__(self, message: str = "存储空间不足"):
        super().__init__(413, message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(_request: Request, _exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"code": -1, "message": "服务器内部错误", "data": None},
        )
