from datetime import datetime, timedelta
from typing import Any, Optional, Union

# 修复bcrypt版本检测问题
try:
    import bcrypt
    # 如果bcrypt没有__about__属性，添加一个模拟的__about__模块
    if not hasattr(bcrypt, '__about__'):
        class DummyAbout:
            __version__ = bcrypt.__version__ if hasattr(bcrypt, '__version__') else '4.3.0'
        bcrypt.__about__ = DummyAbout()
except Exception:
    # 忽略任何错误，passlib会自动降级到其他哈希方案
    pass

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# 使用多种哈希方案，如果bcrypt出错会降级使用SHA256
pwd_context = CryptContext(
    schemes=["bcrypt", "sha256_crypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # 配置bcrypt参数
    sha256_crypt__rounds=80000  # SHA256参数
)


def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    # 捕获可能的bcrypt错误
    try:
        return pwd_context.hash(password)
    except Exception as e:
        # 如果bcrypt出错，记录错误并继续
        print(f"警告: 使用备选哈希方法 - bcrypt可能存在问题: {str(e)}")
        # 强制使用sha256_crypt
        return pwd_context.using(scheme="sha256_crypt").hash(password) 