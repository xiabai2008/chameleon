"""冒烟测试：包可导入、版本号存在。"""

from chameleon import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_import_all_modules() -> None:
    import chameleon.core.config
    import chameleon.core.exceptions
    import chameleon.core.models
    import chameleon.infra.logging
    import chameleon.utils.content_hash
    import chameleon.utils.encoding
    import chameleon.utils.url_utils

    assert chameleon.core.config.settings is not None
