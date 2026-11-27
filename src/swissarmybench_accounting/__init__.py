"""Swiss Army Bench Accounting: a project whose deliverable is an Excel workbook (Plans/editions.plan.md).

Built into Swiss Army Bench (the owner, 2026-11-27: "all extensions should be built in now"): its own package
in the app's one wheel, always on; what it adds is declared in extension.py, which the app reads
(swissarmybench/extensions.py BUILT_IN). At the app's version.
The one workbook builder is the app's sab_excel (Plans/excel.plan.md): the same in the app and, the parts a
design uses, in the workbook.py it exports.
"""

__version__ = "0.0.42"
