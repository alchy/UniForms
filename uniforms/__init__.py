"""
UniForms – generický formulářový engine (FastAPI).

Veřejné API balíčku pro použití jako knihovna:

    from uniforms import create_app, configure, Settings, UniformsConfig

    configure(uniforms_path="moje-konfigurace.yaml")   # volitelné
    app = create_app()                                  # samostatná aplikace
    # nebo: host_app.mount("/forms", create_app())      # sub-aplikace hostitele

Stavební bloky pro hlubší integraci (vlastní storage / auth):
    uniforms.storage.base.StorageBackend     – rozhraní úložiště záznamů
    uniforms.auth.auth_provider.AuthProvider – rozhraní autentizace
    uniforms.services.*                      – doménová logika bez HTTP vrstvy
"""

from uniforms.config import Settings, UniformsConfig, configure, load_uniforms_config
from uniforms.main import create_app

__all__ = [
    "Settings",
    "UniformsConfig",
    "configure",
    "create_app",
    "load_uniforms_config",
]
