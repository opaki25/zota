from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./zota.db'
    redis_url: str = 'redis://localhost:6379/0'
    app_origin: str = 'http://localhost:3000'
    api_root_path: str = ''
    vercel_env: str = ''
    secure_cookies: bool = True
    testing: bool = False
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    mail_from: str = ''
    google_places_api_key: str = ''
    brave_search_api_key: str = ''
    whatsapp_access_token: str = ''
    whatsapp_phone_number_id: str = ''
    whatsapp_template_name: str = ''
    whatsapp_graph_version: str = ''
    cron_secret: str = ''

    @model_validator(mode='after')
    def validate_vercel_environment(self):
        if self.vercel_env in ('production', 'preview'):
            required = {'database_url', 'redis_url', 'app_origin'}
            if required - self.model_fields_set:
                raise ValueError('Vercel requires explicit DATABASE_URL, REDIS_URL, and APP_ORIGIN')
            if not self.database_url.startswith('postgresql+psycopg://'):
                raise ValueError('Vercel requires PostgreSQL using postgresql+psycopg://')
            if not self.app_origin.startswith('https://') or not self.secure_cookies or self.testing:
                raise ValueError('Vercel requires HTTPS APP_ORIGIN, SECURE_COOKIES=true, and TESTING=false')
        if self.api_root_path not in ('', '/api'):
            raise ValueError('API_ROOT_PATH must be empty or /api')
        return self

settings = Settings()
