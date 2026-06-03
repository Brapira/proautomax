import importlib
import pkgutil
import rotinas


def carregar_rotinas():
    registradas = {}

    for module_info in pkgutil.walk_packages(
        rotinas.__path__,
        rotinas.__name__ + "."
    ):
        module = importlib.import_module(module_info.name)

        if hasattr(module, "executar"):
            codigos = getattr(module, "CODIGOS_ROTINA", None) or (
                [module.CODIGO_ROTINA] if hasattr(module, "CODIGO_ROTINA") else []
            )
            for codigo in codigos:
                registradas[codigo] = module.executar

    return registradas
