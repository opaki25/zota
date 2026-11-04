from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./zota.db'
    redis_url: str = 'redis://localhost:6379/0'
    app_origin: str = 'http://localhost:3000'
    secure_cookies: bool = True
    testing: bool = False
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    mail_from: str = ''

settings = Settings()
