"""
Konfigürasyon modülü.
Tüm ayarlar, ortam değişkenleri veya .env dosyası üzerinden okunur.
Asla kod içine gömülü sabit değer kullanılmaz.
"""
from config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
