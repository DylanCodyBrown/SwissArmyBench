"""A made-up Trino on 127.0.0.1 that signs in by client certificate only (mutual TLS: Python's ssl with
CERT_REQUIRED), and the made-up keys, certificates and keystores the tests use. No real server, company
or person: a certificate authority made here signs the server's certificate and the client's.

The stand-in answers `POST /v1/statement` with one finished page (no nextUri): the catalog query
(information_schema) with one table, `lake.sales.orders`; a COUNT(*) with its count; any other query
with the orders' rows.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
import ssl
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

PASSWORD = "made-up-keystore-pass"
CLIENT = "lake-reader"  # the client certificate's common name, as the stand-in saw it
ORDERS: list[list[Any]] = [
    [1, "North", 120.5],
    [2, "South", 80.0],
    [3, "East", 42.25],
    [4, "West", 310.0],
    [5, "North", 15.75],
]
COLUMNS = [("order_id", "bigint"), ("region", "varchar"), ("amount", "double")]


@dataclass
class Material:
    """The made-up authority, the server's certificate and key, and the client's."""

    ca_pem: bytes
    server_pem: bytes
    server_key_pem: bytes
    client_key: rsa.RSAPrivateKey
    client_cert: x509.Certificate
    ca_cert: x509.Certificate


def _name(common: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def _cert(
    subject: str, key: rsa.RSAPrivateKey, issuer: str, signer: rsa.RSAPrivateKey, ca: bool, sans: list[Any]
) -> x509.Certificate:
    now = datetime.datetime.now(datetime.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(_name(issuer))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName(sans), critical=False)
    return builder.sign(signer, hashes.SHA256())


def _pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _key_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def material() -> Material:
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = _cert("Made-up Test CA", ca_key, "Made-up Test CA", ca_key, True, [])
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sans = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    server = _cert("localhost", server_key, "Made-up Test CA", ca_key, False, sans)
    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = _cert(CLIENT, client_key, "Made-up Test CA", ca_key, False, [])
    return Material(_pem(ca), _pem(server), _key_pem(server_key), client_key, client, ca)


def pkcs12_bytes(m: Material, password: str = PASSWORD, alias: str = "lake") -> bytes:
    return pkcs12.serialize_key_and_certificates(
        alias.encode(),
        m.client_key,
        m.client_cert,
        [m.ca_cert],
        serialization.BestAvailableEncryption(password.encode()),
    )


def jks_bytes(
    m: Material, password: str = PASSWORD, aliases: tuple[str, ...] = ("lake",), kind: str = "jks"
) -> bytes:
    """A JKS (or JCEKS) keystore, made with pyjks (the test is skipped where it is not installed)."""
    import jks  # type: ignore[import-untyped]

    der_key = m.client_key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    chain = [c.public_bytes(serialization.Encoding.DER) for c in (m.client_cert, m.ca_cert)]
    entries = [jks.PrivateKeyEntry.new(alias, chain, der_key, "pkcs8") for alias in aliases]
    for entry in entries:
        entry.encrypt(password)
    return bytes(jks.KeyStore.new(kind, entries).saves(password))


def _arguments(kind: str) -> list[dict[str, Any]]:
    """A type's arguments as Trino sends them (a varchar's length)."""
    return [{"kind": "LONG", "value": 2147483647}] if kind == "varchar" else []


def jceks_bytes(m: Material, password: str = PASSWORD) -> bytes:
    """A JCEKS keystore: pyjks writes JKS only, so a JKS with JCEKS's magic and its signature made again
    (SHA-1 over the password as UTF-16BE, "Mighty Aphrodite" and the body, as both formats sign)."""
    import hashlib

    body = b"\xce\xce\xce\xce" + jks_bytes(m, password)[4:-20]
    signed = password.encode("utf-16-be") + b"Mighty Aphrodite" + body
    return body + hashlib.sha1(signed, usedforsecurity=False).digest()


@dataclass
class StandIn:
    """The stand-in Trino, serving HTTPS on 127.0.0.1 and asking every caller for a client certificate."""

    m: Material
    folder: Path
    port: int = 0
    seen: list[dict[str, Any]] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None

    @property
    def ca_file(self) -> Path:
        return self.folder / "made-up-ca.pem"

    def start(self) -> StandIn:
        self.ca_file.write_bytes(self.m.ca_pem)
        (self.folder / "server.pem").write_bytes(self.m.server_pem)
        (self.folder / "server-key.pem").write_bytes(self.m.server_key_pem)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.folder / "server.pem", self.folder / "server-key.pem")
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=str(self.ca_file))
        seen = self.seen

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                sql = self.rfile.read(length).decode()
                peer: Any = getattr(self.connection, "getpeercert", dict)()
                common = dict(x[0] for x in peer.get("subject", ())).get("commonName") if peer else None
                seen.append(
                    {
                        "path": self.path,
                        "sql": sql,
                        "client": common,
                        "user": self.headers.get("X-Trino-User"),
                    }
                )
                if self.path != "/v1/statement":
                    self.send_error(404)
                    return
                low = sql.lower()
                if "information_schema" in low:
                    columns = [
                        ("table_catalog", "varchar"), ("table_schema", "varchar"), ("table_name", "varchar"),
                        ("table_type", "varchar"), ("column_name", "varchar"), ("data_type", "varchar"),
                        ("is_nullable", "varchar"), ("ordinal_position", "bigint"),
                    ]  # fmt: skip
                    data: list[list[Any]] = [
                        ["lake", "sales", "orders", "BASE TABLE", name, kind, "YES", at]
                        for at, (name, kind) in enumerate(COLUMNS, start=1)
                    ]
                elif "count(*)" in low:
                    columns, data = [("_col0", "bigint")], [[len(ORDERS)]]
                else:
                    columns, data = COLUMNS, ORDERS
                body = {
                    "id": "made-up-query",
                    "infoUri": "https://127.0.0.1/ui/query.html",
                    "columns": [
                        {"name": n, "type": t, "typeSignature": {"rawType": t, "arguments": _arguments(t)}}
                        for n, t in columns
                    ],
                    "data": data,
                    "stats": {"state": "FINISHED"},
                }
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        self._server = server
        self.port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
