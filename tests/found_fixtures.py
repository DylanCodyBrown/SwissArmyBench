# ruff: noqa: E501 (the made-up files are written as the tools write them: one long line each)
"""Made-up files the tools a computer has keep their connections in (Find connections on this computer): a
fake home folder laid out as Windows, macOS or Linux keeps them, with decoys the hint scan must never read.
Every password in them is made up and listed in PASSWORDS: no answer, log or written file may hold one."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

PASSWORDS = (
    "MadeUpPw-DBeaver-1",
    "MadeUpPw-Ads-2",
    "MadeUpPw-Tools-3",
    "MadeUpPw-Hint-4",
    "MadeUpPw-Url-5",
    "MadeUpPw-Odbc-6",
    "MadeUpPw-Heidi-7",
    "MadeUpPw-Odc-8",
    "MadeUpPw-Browser-9",
    "MadeUpPw-Ssh-10",
    "MadeUpPw-Pgadmin-11",
    "MadeUpPw-Jdbc-12",
    "MadeUpPw-Workbench-13",
    "MadeUpPw-Credentials-14",
)

DBEAVER = """{
  "folders": {},
  "connections": {
    "postgres-jdbc-18c1": {
      "provider": "postgresql", "driver": "postgres-jdbc", "name": "Shop (dev)", "save-password": true,
      "configuration": {"host": "pg.shop.internal", "port": "5432", "database": "shop",
        "url": "jdbc:postgresql://pg.shop.internal:5432/shop", "user": "analyst",
        "password": "MadeUpPw-DBeaver-1", "type": "dev", "auth-model": "native"}
    },
    "mssql-9a2": {
      "provider": "sqlserver", "driver": "microsoft", "name": "Finance ledger",
      "configuration": {"host": "fin-sql01.corp.internal", "port": "1433", "database": "Ledger",
        "auth-model": "sqlserver_ntlm"}
    },
    "sqlite-3": {
      "provider": "generic", "driver": "sqlite_jdbc", "name": "Local cache",
      "configuration": {"database": "C:\\\\data\\\\cache.sqlite", "url": "jdbc:sqlite:C:\\\\data\\\\cache.sqlite"}
    },
    "mongo-4": {
      "provider": "mongodb", "driver": "mongo", "name": "Events",
      "configuration": {"host": "mongo.events.internal", "port": "27017", "database": "events"}
    }
  }
}"""

REGSRVR = """<?xml version="1.0"?>
<model xmlns="http://schemas.serviceml.org/smlif/2007/02">
  <definitions><document><data>
    <RegisteredServers:RegisteredServer xmlns:RegisteredServers="http://schemas.microsoft.com/sqlserver/RegisteredServers/2007/08">
      <RegisteredServers:Name type="string">Sales warehouse</RegisteredServers:Name>
      <RegisteredServers:ServerName type="string">sales-sql02.corp.internal\\WAREHOUSE</RegisteredServers:ServerName>
      <RegisteredServers:ConnectionStringWithEncryptedPassword type="string">data source=sales-sql02.corp.internal\\WAREHOUSE;initial catalog=SalesDW;user id=report_reader;password=AQAAANCMnd8BFdERjHoAwE;pooling=False</RegisteredServers:ConnectionStringWithEncryptedPassword>
      <RegisteredServers:ServerType type="ServerType">DatabaseEngine</RegisteredServers:ServerType>
    </RegisteredServers:RegisteredServer>
    <RegisteredServers:RegisteredServer xmlns:RegisteredServers="http://schemas.microsoft.com/sqlserver/RegisteredServers/2007/08">
      <RegisteredServers:Name type="string">Finance</RegisteredServers:Name>
      <RegisteredServers:ServerName type="string">FIN-SQL01.corp.internal</RegisteredServers:ServerName>
      <RegisteredServers:ConnectionStringWithEncryptedPassword type="string">data source=FIN-SQL01.corp.internal;initial catalog=ledger;integrated security=True</RegisteredServers:ConnectionStringWithEncryptedPassword>
      <RegisteredServers:ServerType type="ServerType">DatabaseEngine</RegisteredServers:ServerType>
    </RegisteredServers:RegisteredServer>
    <RegisteredServers:RegisteredServer xmlns:RegisteredServers="http://schemas.microsoft.com/sqlserver/RegisteredServers/2007/08">
      <RegisteredServers:Name type="string">Cube</RegisteredServers:Name>
      <RegisteredServers:ServerName type="string">olap01</RegisteredServers:ServerName>
      <RegisteredServers:ServerType type="ServerType">AnalysisServices</RegisteredServers:ServerType>
    </RegisteredServers:RegisteredServer>
  </data></document></definitions>
</model>"""

SSMS_RECENT = """<?xml version="1.0" encoding="utf-8"?>
<SqlStudio><SSMS><ConnectionOptions><ServerTypes><Element><Value><ServerTypeItem><Servers>
  <Element><Item><ServerConnectionItem>
    <Instance>hr-sql03.corp.internal</Instance>
    <AuthenticationMethod>1</AuthenticationMethod>
    <Connections><Element><Item><ServerConnectionSettings>
      <UserName>hr_viewer</UserName>
      <AuthenticationMethod>1</AuthenticationMethod>
      <Database>People</Database>
      <ConnectionStringWithEncryptedPassword>data source=hr-sql03.corp.internal;password=AQAAANCMnd8;user id=hr_viewer</ConnectionStringWithEncryptedPassword>
    </ServerConnectionSettings></Item></Element></Connections>
  </ServerConnectionItem></Item></Element>
</Servers></ServerTypeItem></Value></Element></ServerTypes></ConnectionOptions></SSMS></SqlStudio>"""

ADS_SETTINGS = """{
  // Azure Data Studio's own settings, with comments and a trailing comma
  "workbench.colorTheme": "Default Dark",
  "datasource.connections": [
    {
      "options": {
        "connectionName": "Ops on Azure",
        "server": "ops-made-up.database.windows.net",
        "database": "Operations",
        "authenticationType": "SqlLogin",
        "user": "ops_reader",
        "password": "MadeUpPw-Ads-2",
      },
      "providerName": "MSSQL",
      "groupId": "C777F06B-202E-4480-B475-FA416154D458",
    },
  ],
}"""

VSCODE_SETTINGS = """{
  "editor.fontSize": 14,
  /* the mssql extension */
  "mssql.connections": [
    {"server": "fin-sql01.corp.internal", "database": "Ledger", "authenticationType": "Integrated",
     "profileName": "Ledger (VS Code)"}
  ],
  "sqltools.connections": [
    {"name": "Shop reporting", "driver": "MySQL", "server": "mysql.shop.internal", "port": 3306,
     "database": "reporting", "username": "reporter", "password": "MadeUpPw-Tools-3"},
    {"name": "Notes", "driver": "SQLite", "database": "/home/someone/notes.db"}
  ]
}"""

JETBRAINS = """<?xml version="1.0" encoding="UTF-8"?>
<application>
  <component name="dataSourceStorage">
    <data-source source="LOCAL" name="inventory@pg.shop.internal" uuid="1f2e3d4c">
      <driver-ref>postgresql</driver-ref>
      <jdbc-driver>org.postgresql.Driver</jdbc-driver>
      <jdbc-url>jdbc:postgresql://pg.shop.internal:5432/inventory?password=MadeUpPw-Jdbc-12</jdbc-url>
    </data-source>
  </component>
</application>"""

JETBRAINS_LOCAL = """<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="dataSourceStorageLocal">
    <data-source name="inventory@pg.shop.internal" uuid="1f2e3d4c">
      <user-name>stock_clerk</user-name>
    </data-source>
  </component>
</project>"""

JETBRAINS_RECENT = """<application><component name="RecentProjectsManager"><option name="additionalInfo"><map>
  <entry key="$USER_HOME$/IdeaProjects/orders-service"><value><RecentProjectMetaInfo /></value></entry>
</map></option></component></application>"""

PROJECT_SOURCES = """<?xml version="1.0" encoding="UTF-8"?>
<project version="4"><component name="DataSourceManagerImpl" format="xml" multifile-model="true">
  <data-source source="LOCAL" name="orders" uuid="77aa">
    <driver-ref>oracle</driver-ref>
    <jdbc-url>jdbc:oracle:thin:@//ora.orders.internal:1521/ORDERS</jdbc-url>
  </data-source>
</component></project>"""

WORKBENCH = """<?xml version="1.0"?>
<data grt_format="2.0">
  <value _ptr_="0x1" type="list" content-type="object" content-struct-name="db.mgmt.Connection">
    <value type="object" struct-name="db.mgmt.Connection" id="a1">
      <link type="object" struct-name="db.mgmt.Driver" key="driver">com.mysql.rdbms.mysql.driver.native</link>
      <value type="string" key="name">Shop reporting (Workbench)</value>
      <value _ptr_="0x2" type="dict" key="parameterValues">
        <value type="string" key="hostName">mysql.shop.internal</value>
        <value type="int" key="port">3306</value>
        <value type="string" key="schema">reporting</value>
        <value type="string" key="userName">reporter</value>
        <value type="string" key="password">MadeUpPw-Workbench-13</value>
      </value>
    </value>
  </value>
</data>"""

HEIDI_PORTABLE = """\
Servers\\Shop\\Host<|||>1<|||>maria.shop.internal
Servers\\Shop\\User<|||>1<|||>shop_app
Servers\\Shop\\Password<|||>1<|||>MadeUpPw-Heidi-7
Servers\\Shop\\Port<|||>1<|||>3306
Servers\\Shop\\NetType<|||>3<|||>0
Servers\\Shop\\Databases<|||>1<|||>shop;archive
"""

ODBC_INI = """\
[ODBC Data Sources]
Inventory = PostgreSQL Unicode
Legacy = Made Up Legacy Driver

[Inventory]
Driver = /usr/lib/x86_64-linux-gnu/odbc/psqlodbcw.so
Servername = pg.shop.internal
Port = 5432
Database = inventory
Username = stock_clerk
Password = MadeUpPw-Odbc-6

[Legacy]
Driver = /opt/legacy/libmadeup.so
Server = legacy01
Database = archive
"""

ODC = """<html xmlns:o="urn:schemas-microsoft-com:office:office">
<head><meta http-equiv=Content-Type content="text/x-ms-odc; charset=utf-8">
<xml id=msodc><odc:OfficeDataConnection xmlns:odc="urn:schemas-microsoft-com:office:odc">
<odc:Connection odc:Type="OLEDB">
<odc:ConnectionString>Provider=SQLOLEDB.1;Persist Security Info=True;User ID=budget_reader;Password=MadeUpPw-Odc-8;Initial Catalog=Budget;Data Source=plan-sql04.corp.internal</odc:ConnectionString>
<odc:CommandType>Table</odc:CommandType>
</odc:Connection></odc:OfficeDataConnection></xml></head></html>"""

UDL = (
    "[oledb]\r\n; Everything after this line is an OLE DB initstring\r\n"
    "Provider=MSOLEDBSQL.1;Integrated Security=SSPI;Initial Catalog=Payroll;Data Source=pay-sql05\r\n"
)

DSN_FILE = """[ODBC]
DRIVER=ODBC Driver 18 for SQL Server
SERVER=crm-sql06.corp.internal
DATABASE=Crm
Trusted_Connection=Yes
"""

# The hint scan's find: a program's own settings, with a connection string, a database URL and an object.
HINT_CONFIG = """<?xml version="1.0"?>
<configuration>
  <connectionStrings>
    <add name="Orders" connectionString="Server=orders-sql07.corp.internal;Database=Orders;User Id=orders_app;Password=MadeUpPw-Hint-4;" />
  </connectionStrings>
</configuration>"""
HINT_JSON = """{
  "reporting": {"database_url": "postgresql://metrics:MadeUpPw-Url-5@metrics.corp.internal:5432/metrics"},
  "warehouse": {"host": "wh.corp.internal", "port": 5439, "database": "dw", "user": "loader"},
  "example": {"host": "your-server", "port": 1433, "database": "my_database"}
}"""


def windows_home(home: Path) -> Path:
    """A Windows user's folders under `home`: every tool above, and the decoys."""
    roaming = home / "AppData" / "Roaming"
    local = home / "AppData" / "Local"
    write(roaming / "DBeaverData/workspace6/General/.dbeaver/data-sources.json", DBEAVER)
    # DBeaver's credentials file: never read (a made-up password in it proves it).
    write(
        roaming / "DBeaverData/workspace6/General/.dbeaver/credentials-config.json",
        '{"postgres-jdbc-18c1": {"#connection": {"user": "analyst", "password": "MadeUpPw-Credentials-14"}}}',
    )
    write(roaming / "Microsoft/SQL Server Management Studio/19.0/RegSrvr.xml", REGSRVR)
    write(roaming / "Microsoft/SQL Server Management Studio/19.0/UserSettings.xml", SSMS_RECENT)
    (roaming / "Microsoft/SQL Server Management Studio/18.0").mkdir(parents=True, exist_ok=True)
    (roaming / "Microsoft/SQL Server Management Studio/18.0/SqlStudio.bin").write_bytes(b"\x00\x01binary")
    write(roaming / "azuredatastudio/User/settings.json", ADS_SETTINGS)
    write(roaming / "Code/User/settings.json", VSCODE_SETTINGS)
    write(roaming / "JetBrains/DataGrip2026.1/options/dataSources.xml", JETBRAINS)
    write(roaming / "JetBrains/DataGrip2026.1/options/dataSources.local.xml", JETBRAINS_LOCAL)
    write(roaming / "JetBrains/DataGrip2026.1/options/recentProjects.xml", JETBRAINS_RECENT)
    write(home / "IdeaProjects/orders-service/.idea/dataSources.xml", PROJECT_SOURCES)
    write(roaming / "MySQL/Workbench/connections.xml", WORKBENCH)
    write(home / "Program Files/HeidiSQL/portable_settings.txt", HEIDI_PORTABLE)
    write(home / "Documents/My Data Sources/Budget.odc", ODC)
    (home / "Documents/My Data Sources/Payroll.udl").write_bytes(UDL.encode("utf-16"))
    write(home / "Program Files/Common Files/ODBC/Data Sources/CRM.dsn", DSN_FILE)
    pgadmin(roaming / "pgAdmin" / "pgadmin4.db")
    # The hint scan's finds.
    write(roaming / "OrdersTool/app.config", HINT_CONFIG)
    write(local / "MetricsAgent/conf/settings.json", HINT_JSON)
    decoys(roaming, local, home)
    return home


def decoys(roaming: Path, local: Path, home: Path) -> None:
    """What must never be looked at: a browser's profile, .ssh, a password manager, a big file, a binary."""
    write(local / "Google/Chrome/User Data/Default/Preferences.json", BROWSER_DECOY)
    write(roaming / "Mozilla/Firefox/Profiles/x.default/prefs.json", BROWSER_DECOY)
    write(roaming / "Bitwarden/data.json", BROWSER_DECOY)
    write(home / ".ssh/config.conf", "Host db\n  HostName decoy-ssh.internal # MadeUpPw-Ssh-10\n")
    write(roaming / ".ssh/known.json", BROWSER_DECOY)
    big = "Server=decoy-big.internal;Database=Big;Password=MadeUpPw-Browser-9;" + " " * (300 * 1024)
    write(roaming / "BigTool/huge.json", big)
    (roaming / "BinTool").mkdir(parents=True, exist_ok=True)
    (roaming / "BinTool/state.json").write_bytes(b"\x00\x00Server=decoy-bin.internal;Database=Bin;")
    write(roaming / "SwissArmyBench/library/connections/x.json", BROWSER_DECOY)


BROWSER_DECOY = (
    '{"saved": "Server=decoy-browser.internal;Database=Secret;Password=MadeUpPw-Browser-9;",'
    ' "url": "postgresql://u:MadeUpPw-Browser-9@decoy-browser.internal/db"}'
)


def linux_home(home: Path) -> Path:
    write(home / ".local/share/DBeaverData/workspace6/General/.dbeaver/data-sources.json", DBEAVER)
    write(home / ".odbc.ini", ODBC_INI)
    write(home / ".config/Code/User/settings.json", VSCODE_SETTINGS)
    write(home / ".config/OrdersTool/app.config", HINT_CONFIG)
    write(home / ".config/google-chrome/Default/prefs.json", BROWSER_DECOY)
    pgadmin(home / ".pgadmin" / "pgadmin4.db")
    return home


def pgadmin(path: Path) -> None:
    """pgAdmin 4's database, made here: a server table with a password column that must never be read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE server (id INTEGER PRIMARY KEY, name TEXT, host TEXT, port INTEGER, maintenance_db TEXT,"
        " username TEXT, password TEXT)"
    )
    db.execute(
        "INSERT INTO server (name, host, port, maintenance_db, username, password) VALUES "
        "('Shop (pgAdmin)', 'pg.shop.internal', 5432, 'shop', 'analyst', 'MadeUpPw-Pgadmin-11')"
    )
    db.commit()
    db.close()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FakeRegistry:
    """Windows' registry as a dictionary: (hive, path) -> {value: data}; a key's subkeys are the paths below it.
    Every value a test puts here can be read; the finder must ask only for the named ones."""

    def __init__(self, keys: dict[tuple[str, str], dict[str, str]]) -> None:
        self.keys = {(h, p.casefold()): v for (h, p), v in keys.items()}
        self.paths = {(h, p.casefold()): p for (h, p) in keys}
        self.asked: list[tuple[str, str, tuple[str, ...] | None]] = []

    def subkeys(self, hive: str, path: str, view: int) -> list[str]:
        prefix = path.casefold() + "\\"
        found = []
        for (h, p), real in self.paths.items():
            if h == hive and p.startswith(prefix) and "\\" not in p[len(prefix) :]:
                found.append(real.split("\\")[-1])
        return found

    def values(self, hive: str, path: str, view: int, names: Iterable[str] | None) -> dict[str, str]:
        listed = tuple(names) if names is not None else None
        self.asked.append((hive, path, listed))
        values = self.keys.get((hive, path.casefold()), {})
        return dict(values) if listed is None else {k: v for k, v in values.items() if k in listed}


REGISTRY = {
    ("HKCU", r"SOFTWARE\ODBC\ODBC.INI\ODBC Data Sources"): {
        "Stock": "SQL Server",
        "Mainframe": "IBM DB2 ODBC",
    },
    ("HKCU", r"SOFTWARE\ODBC\ODBC.INI\Stock"): {
        "Driver": r"C:\Windows\system32\SQLSRV32.dll",
        "Server": "stock-sql08.corp.internal",
        "Database": "Stock",
        "LastUser": "stock_reader",
        "PWD": "MadeUpPw-Odbc-6",
    },
    ("HKCU", r"SOFTWARE\ODBC\ODBC.INI\Mainframe"): {"Driver": r"C:\IBM\db2cli.dll", "Description": "Host"},
    ("HKCU", r"Software\HeidiSQL\Servers\Reports"): {
        "Host": "reports-pg.corp.internal",
        "User": "viewer",
        "Port": "5432",
        "NetType": "8",
        "Password": "MadeUpPw-Heidi-7",
    },
}
