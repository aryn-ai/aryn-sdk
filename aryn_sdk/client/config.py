from os import PathLike
import os
from pathlib import Path
from typing import Optional
import yaml

_DEFAULT_PATH = Path.home() / ".aryn" / "config.yaml"
_ARYN_API_KEY_ENV_VAR = "ARYN_API_KEY"
_ARYN_URL_ENV_VAR = "ARYN_API_URL"
_DEFAULT_ARYN_URL = "https://api.aryn.ai"


class ArynConfig:
    def __init__(
        self,
        aryn_config_path: PathLike = _DEFAULT_PATH,
        aryn_api_key: Optional[str] = None,
        aryn_url: Optional[str] = None,
    ):
        self._aryn_config_path = Path(aryn_config_path)
        self._aryn_api_key = aryn_api_key
        self._aryn_url = aryn_url

    def api_key(self) -> str:
        if self._aryn_api_key is not None:
            return self._aryn_api_key
        if val := os.getenv(_ARYN_API_KEY_ENV_VAR):
            return val
        if Path(self._aryn_config_path).exists():
            with open(self._aryn_config_path, "r") as f:
                data = yaml.safe_load(f)
                if "aryn_token" in data:
                    return data["aryn_token"]
        raise ValueError(
            f"Could not find an aryn api key. Checked the {_ARYN_API_KEY_ENV_VAR} env "
            f"var, the {self._aryn_config_path} config file, and the aryn_api_key parameter"
        )

    def aryn_url(self) -> str:
        url = None

        if self._aryn_url is not None:
            url = self._aryn_url
        elif val := os.getenv(_ARYN_URL_ENV_VAR):
            url = val
        elif Path(self._aryn_config_path).exists():
            with open(self._aryn_config_path, "r") as f:
                data = yaml.safe_load(f)
                if "aryn_url" in data:
                    url = data["aryn_url"]
        else:
            url = _DEFAULT_ARYN_URL

        if url is None:
            raise ValueError(
                f"Could not find an aryn url. Checked the {_ARYN_URL_ENV_VAR} env "
                f"var, the {self._aryn_config_path} config file, and the aryn_url parameter"
            )

        return url
