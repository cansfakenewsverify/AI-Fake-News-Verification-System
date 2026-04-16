"""
對外整合用的穩定封裝層。

其他系統請優先 import `factcheck_system`，避免直接耦合內部 `app.*` 結構。
"""

from app import __version__ as __version__

from factcheck_system.crawler import CrawlerClient as CrawlerClient
from factcheck_system.services import AIClient as AIClient

