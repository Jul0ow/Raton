import os


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante : {name}")
    return value


class Settings:
    def __init__(self) -> None:
        self.database_url = _env("DATABASE_URL")
        self.oidc_issuer = _env("OIDC_ISSUER")
        self.oidc_audience = _env("OIDC_AUDIENCE")
        self.ai_endpoint = _env("AI_ENDPOINT")
        self.ai_api_key = _env("AI_API_KEY")
        self.directory_url = _env("DIRECTORY_URL")
        self.directory_token = _env("DIRECTORY_TOKEN")
        self.compta_url = _env("COMPTA_URL")
        self.compta_token = _env("COMPTA_TOKEN")
        self.s3_endpoint = _env("S3_ENDPOINT")
        self.s3_bucket = _env("S3_BUCKET")
        # Les identifiants S3 sont lus par boto3 dans AWS_ACCESS_KEY_ID et AWS_SECRET_ACCESS_KEY.


settings = Settings()
