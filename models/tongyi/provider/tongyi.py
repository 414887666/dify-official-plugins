import logging

from dify_plugin import ModelProvider
from dify_plugin.errors.model import CredentialsValidateFailedError

from models._common import get_compatible_base_url, get_dashscope_base_address

logger = logging.getLogger(__name__)


class TongyiProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials

        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            if not str(credentials.get("dashscope_api_key") or "").strip():
                raise CredentialsValidateFailedError("dashscope_api_key is required")

            get_dashscope_base_address(credentials)

            if str(credentials.get("compatible_endpoint_url") or "").strip():
                get_compatible_base_url(credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            try:
                provider_name = self.get_provider_schema().provider
            except Exception:
                provider_name = "tongyi"
            logger.exception(f"{provider_name} credentials validate failed")
            raise CredentialsValidateFailedError(str(ex))
