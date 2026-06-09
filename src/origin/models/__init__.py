"""SQLAlchemy ORM models for the 7 Origin tables.

Importing this module registers all models on the shared Base.metadata so
Alembic autogeneration sees them.
"""

from origin.models.person import Person
from origin.models.platform_setting import PlatformSetting
from origin.models.passkey_credential import PasskeyCredential
from origin.models.otp_code import OtpCode
from origin.models.api_key import ApiKey
from origin.models.server_credential import ServerCredential
from origin.models.grant import Grant

__all__ = [
    "Person",
    "PlatformSetting",
    "PasskeyCredential",
    "OtpCode",
    "ApiKey",
    "ServerCredential",
    "Grant",
]
