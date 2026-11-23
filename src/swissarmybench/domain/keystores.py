"""A connection that signs in with a client certificate kept in a keystore file (Trino's second way to
sign in, the owner, 2026-11-16: "my trino connection uses a keystore file ... I have saved it to the
function app, it is not in the vault").

The keystore is read by code that travels INSIDE the connection's own code (KEYSTORE_FILES below), so it
runs the same in the app, a Workbench kernel, an exported script and an Azure Function:

  format     told by the file's first bytes, never its name: JKS (0xFEEDFEED), JCEKS (0xCECECECE),
             else PKCS#12 (.p12, .pfx: a DER sequence, 0x30). PKCS#12 is read with `cryptography`;
             JKS and JCEKS with `pyjks`, a package of the connection (offered with Install, as every
             connection's driver is), never one of the app
  the entry  its one private key, or the alias named when it holds several
  the files  the key and its certificate chain as two PEM files in a folder only the user can read
             (0700, the files 0600; on Windows the user's own temporary folder), removed when the
             Python ends (atexit): the key lands nowhere else
  the path   a setting (`keystore = r"..."`), or, when the user maps it, an environment variable with
             this computer's path as its default: `os.environ.get("TRINO_KEYSTORE_PATH", r"C:\\...")`,
             so a function app sets the path where the file sits there (domain/certificate_files.py,
             as every certificate file may). The file is never copied
  password   always `secret("TRINO_KEYSTORE_PASSWORD")`: the keyring, the environment or a vault

From a key vault (the owner, 2026-11-20: "we need to make it possible that certificates can be retrieved
from the vault for the Trino connection"), Trino's third way to sign in (TRINO_VAULT):

  the value  `keystore = os.environ["TRINO_CLIENT_CERTIFICATE"]`, a `${NAME}` (12.7) the form points at a
             vault's variable. Azure Key Vault keeps a certificate with its private key as a secret whose
             value is the base64 PKCS#12 (content type application/x-pkcs12), or PEM text: the same
             keystore_files reads a value that is not a file's path as base64 PKCS#12 or JKS (told by
             the decoded first bytes), or as PEM with a BEGIN line. The bytes land only in the two 0600
             files above: never the library, a project, a log or an answer (an error never says them)
  password   its own variable, `keystore_password = os.environ["NAME"]` from its box's `${NAME}`: none
             by default (Key Vault's own exports have none). A password is never a setting, except this
             one written as a variable: the form's box takes `${NAME}` or nothing, never a typed value
             (blades.py)
  where      on a Function App the vault is read by its managed identity (the export's FROM_VAULTS), so
             this way carries no "only works on your machine" note: nothing of it is on this disk

Pure text and rules: no I/O.
"""

from __future__ import annotations

JKS_MAGIC: bytes = b"\xfe\xed\xfe\xed"
JCEKS_MAGIC: bytes = b"\xce\xce\xce\xce"

# The variable the keystore's path is offered as (domain/certificate_files.py), and its password's name.
PATH_VARIABLE: str = "TRINO_KEYSTORE_PATH"
PASSWORD_NAME: str = "TRINO_KEYSTORE_PASSWORD"  # noqa: S105 (a secret's name, never its value)
MARK: str = "CertificateAuthentication"  # how the form tells this way to sign in from the others
# The key vault's way: the keystore is a variable's value (the form's sign-in tells it by VAULT_MARK, tried
# before MARK, which its code holds too).
VAULT_VARIABLE: str = "TRINO_CLIENT_CERTIFICATE"
VAULT_MARK: str = 'keystore = os.environ["'


def keystore_format(data: bytes) -> str:
    """JKS, JCEKS, PEM, PKCS#12, or "" (none of those), by the first bytes."""
    if data[:4] == JKS_MAGIC:
        return "JKS"
    if data[:4] == JCEKS_MAGIC:
        return "JCEKS"
    if b"-----BEGIN" in data[:4096]:
        return "PEM"
    if data[:1] == b"\x30":
        return "PKCS#12"
    return ""


# The helper written into the connection's code. Standard library and cryptography; pyjks for JKS.
KEYSTORE_FILES = '''def keystore_files(path, password, alias=""):
    """The keystore's private key and certificate chain as two PEM files only you can read, removed
    when this Python ends: (certificate, key). PKCS#12, JKS, JCEKS or PEM, told by the first bytes.
    `path`: the keystore's file, or the keystore itself as a key vault keeps a certificate (base64
    PKCS#12 or JKS, or PEM text)."""
    import atexit
    import base64
    import os
    import shutil
    import tempfile

    if os.path.isfile(path):
        with open(path, "rb") as file:
            data = file.read()
    else:  # a key vault's certificate (a variable's value): base64 PKCS#12 or JKS, or PEM text
        text = path.strip()
        data = b""
        if "-----BEGIN" in text:
            # A PEM kept as a key vault SECRET (the owner, 2026-11-20): the portal's one-line box loses its
            # line breaks (spaces instead) or keeps them as the two letters \\n; each block is laid out again
            # (its base64 joined and cut at 64), so either reads as the file did.
            import re

            text = text.replace("\\\\r\\\\n", "\\n").replace("\\\\n", "\\n").replace("\\r", "")

            def _laid_out(found):
                body = "".join(found.group(2).split())
                lines = "\\n".join(body[i : i + 64] for i in range(0, len(body), 64))
                return f"-----BEGIN {found.group(1)}-----\\n{lines}\\n-----END {found.group(1)}-----\\n"

            if "\\n" not in text:  # one line: its breaks were spaces
                block = r"-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \\1-----"
                text = re.sub(block, _laid_out, text, flags=re.S)
            data = text.encode()
        else:
            try:
                raw = base64.b64decode("".join(text.split()), validate=True)
            except ValueError:
                raw = b""
            known = raw[:1] == b"\\x30" or raw[:4] in (b"\\xfe\\xed\\xfe\\xed", b"\\xce\\xce\\xce\\xce")
            if len(raw) >= 32 and (known or b"-----BEGIN" in raw[:4096]):
                data = raw
        if not data:
            named = sorted(k for k, v in os.environ.items() if v == path)
            if len(path) < 400 and "\\n" not in path:
                raise FileNotFoundError(
                    f"No keystore file at {path}" + (f" (from {', '.join(named)})" if named else "") + ". "
                    "Choose it again here; where the code runs elsewhere (a function app), set its variable "
                    "to the file's path there."
                )
            raise ValueError(  # never the value itself: it may hold a key
                "The keystore" + (f" from {', '.join(named)}" if named else "") + " is neither a "
                "file's path nor a certificate: a key vault keeps one as base64 PKCS#12 (or JKS), or as "
                "PEM text with its private key."
            )
    magic = data[:4]
    if magic in (b"\\xfe\\xed\\xfe\\xed", b"\\xce\\xce\\xce\\xce"):
        kind = "JKS" if magic == b"\\xfe\\xed\\xfe\\xed" else "JCEKS"
        try:
            import jks
        except ImportError:
            raise ImportError(
                f"The keystore is {kind}: reading it needs the pyjks package (pip install pyjks)."
            ) from None
        try:
            store = jks.KeyStore.loads(data, password)
        except jks.KeystoreSignatureException:
            raise ValueError("The keystore's password is wrong.") from None
        except Exception as error:
            raise ValueError(f"The {kind} keystore could not be read: {error}") from None
        keys = dict(store.private_keys)
        if not keys:
            raise ValueError("The keystore holds no private key: only certificates.")
        if alias and alias not in keys:
            raise ValueError(
                f"The keystore has no private key named {alias}: it has {', '.join(sorted(keys))}."
            )
        if not alias and len(keys) > 1:
            raise ValueError(
                f"The keystore holds {len(keys)} private keys ({', '.join(sorted(keys))}): "
                "name the one to use."
            )
        entry = keys[alias or next(iter(keys))]
        if not entry.is_decrypted():
            try:
                entry.decrypt(password)
            except Exception:
                raise ValueError(
                    "The key's password is not the keystore's: the key could not be opened."
                ) from None
        key = entry.pkey_pkcs8
        chain = [der for _, der in entry.cert_chain]
    elif b"-----BEGIN" in data[:4096]:  # PEM: the certificates and the private key, as text
        import re

        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
            load_pem_private_key,
        )

        try:
            found = x509.load_pem_x509_certificates(data)
        except ValueError:
            found = []
        pattern = rb"-----BEGIN ((?:[A-Z]+ )*)PRIVATE KEY-----.+?-----END \\1PRIVATE KEY-----"
        block = re.search(pattern, data, re.S)
        if block is None or not found:
            raise ValueError("The PEM holds no private key with its certificate.")
        try:
            loaded = load_pem_private_key(block.group(0), password.encode() if password else None)
        except TypeError:  # a password for a key that has none, or none for one that has
            if not password:
                raise ValueError("The PEM's private key is encrypted: give its password.") from None
            loaded = load_pem_private_key(block.group(0), None)
        except ValueError:
            raise ValueError("The PEM's password is wrong: its private key could not be opened.") from None
        spki = PublicFormat.SubjectPublicKeyInfo
        mine = loaded.public_key().public_bytes(Encoding.DER, spki)
        found.sort(key=lambda c: c.public_key().public_bytes(Encoding.DER, spki) != mine)  # the leaf first
        key = loaded.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
        chain = [c.public_bytes(Encoding.DER) for c in found]
    elif magic[:1] == b"\\x30":
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

        try:
            store = pkcs12.load_pkcs12(data, password.encode() if password else None)
        except ValueError:
            raise ValueError(
                "The keystore's password is wrong (or the file is not a PKCS#12 keystore)."
            ) from None
        if store.key is None or store.cert is None:
            raise ValueError("The keystore holds no private key with its certificate.")
        name = store.cert.friendly_name.decode() if store.cert.friendly_name else ""
        if alias and name and alias != name:
            raise ValueError(f"The keystore has no private key named {alias}: it has {name}.")
        key = store.key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
        chain = [c.certificate.public_bytes(Encoding.DER) for c in (store.cert, *store.additional_certs)]
    else:
        raise ValueError(
            "The keystore's format is not known: it is not PKCS#12 (.p12, .pfx), JKS, JCEKS or PEM."
        )

    def pem(label, der):
        lines = base64.encodebytes(der).decode().replace("\\n", "")
        body = "\\n".join(lines[i : i + 64] for i in range(0, len(lines), 64))
        return f"-----BEGIN {label}-----\\n{body}\\n-----END {label}-----\\n"

    folder = tempfile.mkdtemp(prefix="sab-keystore-")  # only you can read it (0700)
    atexit.register(shutil.rmtree, folder, True)
    made = []
    for file_name, text in (
        ("certificate.pem", "".join(pem("CERTIFICATE", der) for der in chain)),
        ("key.pem", pem("PRIVATE KEY", key)),
    ):
        made.append(os.path.join(folder, file_name))
        handle = os.open(made[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, "w") as file:
            file.write(text)
    return made[0], made[1]
'''

# Trino's ways to sign in (server/blade_templates.py): the user's password, or the client certificate
# (from a key vault, or a keystore file on this computer).
TRINO_BASIC = """import requests
import trino

user = "my_user"
verify = ""  # the certificate authority's .pem; empty: the system's own
trust_server_certificate = False

session = requests.Session()
session.verify = False if trust_server_certificate else (verify or True)
session.trust_env = False  # this .pem, even where REQUESTS_CA_BUNDLE names another

conn = trino.dbapi.connect(
    host="my-server",
    port=443,
    user=user,
    catalog="hive",
    http_scheme="https",
    auth=trino.auth.BasicAuthentication(user, secret("password")),
    http_session=session,
    request_timeout=600,  # seconds: a long query is not cut off (the client's own default is 30)
)"""

# No password and no client certificate: only the server's certificate checked, against its root certificate
# authority (the owner, 2026-11-20: "my .pem is the root CA with no password" / "this file is the only
# connection option I need"). Its root CA: a file's path, or `${NAME}` from a key vault (certificate_file).
TRINO_ROOT_CA = """import requests
import trino

user = "my_user"  # the name Trino records your queries under (no password is sent)
verify = ""  # the root CA's .pem: a file's path, or a key vault's secret (${NAME}); empty: the system's
trust_server_certificate = False

session = requests.Session()
session.verify = False if trust_server_certificate else (verify or True)
session.trust_env = False  # this .pem, even where REQUESTS_CA_BUNDLE names another

conn = trino.dbapi.connect(
    host="my-server",
    port=443,
    user=user,
    catalog="hive",
    http_scheme="https",
    auth=None,  # no sign-in: the connection is trusted by the server's certificate alone
    http_session=session,
    request_timeout=600,  # seconds: a long query is not cut off (the client's own default is 30)
)"""
ROOT_CA_MARK = "auth=None,  # no sign-in"

TRINO_KEYSTORE = f"""import requests
import trino

user = "my_user"
keystore = r"C:\\certs\\my.keystore"
keystore_alias = ""  # the entry to use when the keystore holds more than one key
verify = ""  # the certificate authority's .pem; empty: the system's own
trust_server_certificate = False


{KEYSTORE_FILES}

session = requests.Session()
session.verify = False if trust_server_certificate else (verify or True)
session.trust_env = False  # this .pem, even where REQUESTS_CA_BUNDLE names another

certificate, private_key = keystore_files(keystore, secret("{PASSWORD_NAME}"), keystore_alias)
conn = trino.dbapi.connect(
    host="my-server",
    port=443,
    user=user,
    catalog="hive",
    http_scheme="https",
    auth=trino.auth.{MARK}(certificate, private_key),
    http_session=session,
    request_timeout=600,  # seconds: a long query is not cut off (the client's own default is 30)
)"""

TRINO_VAULT = f"""import os

import requests
import trino

user = "my_user"
keystore = os.environ["{VAULT_VARIABLE}"]  # a key vault's certificate: base64 PKCS#12, or PEM
keystore_password = ""  # its variable when it has one (${{NAME}}); Key Vault's own have none
keystore_alias = ""  # the entry to use when the keystore holds more than one key
verify = ""  # the certificate authority's .pem (a key vault's too); empty: the system's own
trust_server_certificate = False


{KEYSTORE_FILES}

session = requests.Session()
session.verify = False if trust_server_certificate else (verify or True)
session.trust_env = False  # this .pem, even where REQUESTS_CA_BUNDLE names another

certificate, private_key = keystore_files(keystore, keystore_password, keystore_alias)
conn = trino.dbapi.connect(
    host="my-server",
    port=443,
    user=user,
    catalog="hive",
    http_scheme="https",
    auth=trino.auth.{MARK}(certificate, private_key),
    http_session=session,
    request_timeout=600,  # seconds: a long query is not cut off (the client's own default is 30)
)"""

# The key vault's way before the file's: its code holds MARK too, and the form takes the first that fits.
SIGN_INS: tuple[tuple[str, str, str], ...] = (
    ("Username and password", "BasicAuthentication", TRINO_BASIC),
    ("Root certificate only (no password)", ROOT_CA_MARK, TRINO_ROOT_CA),
    ("Client certificate (from a key vault)", VAULT_MARK, TRINO_VAULT),
    ("Client certificate (a file on this computer)", MARK, TRINO_KEYSTORE),
)
