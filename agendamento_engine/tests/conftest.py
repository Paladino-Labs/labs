"""conftest.py — carrega .env.test.txt antes de qualquer módulo de teste ser importado.

Isso garante que ASAAS_API_KEY e ASAAS_API_URL estejam disponíveis em
os.environ quando pytest.mark.skipif avaliar os decoradores de skip sandbox.
"""
from pathlib import Path

_env_test = Path(__file__).parent.parent / ".env.test.txt"
if _env_test.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_test, override=False)
    except ImportError:
        pass
