"""The client, imported from notebooks and scripts: `import swissarmybench as sab`.

`watch()` (started by itself in a notebook) lists your tables in the grid's Open list. `push(orders)`
sends one by hand and names the dataset (and the tab) after the variable, "orders".
"""

from swissarmybench.client.push_client import DatasetTooLargeError, ServerNotRunningError, push
from swissarmybench.client.watcher import start as watch
from swissarmybench.client.watcher import stop as unwatch

__all__ = ["DatasetTooLargeError", "ServerNotRunningError", "push", "unwatch", "watch"]
