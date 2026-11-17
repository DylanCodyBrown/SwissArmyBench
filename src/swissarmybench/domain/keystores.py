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

Pure text and rules: no I/O.
"""

from __future__ import annotations

JKS_MAGIC: bytes = b"\xfe\xed\xfe\xed"
JCEKS_MAGIC: bytes = b"\xce\xce\xce\xce"

# The variable the keystore's path is offered as (domain/certificate_files.py), and its password's name.
PATH_VARIABLE: str = "TRINO_KEYSTORE_PATH"
PASSWORD_NAME: str = "TRINO_KEYSTORE_PASSWORD"  # noqa: S105 (a secret's name, never its value)
MARK: str = "CertificateAuthentication"  # how the form tells this way to sign in from the others


def keystore_format(data: bytes) -> str:
    """JKS, JCEKS, PKCS#12, or "" (none of those), by the file's first bytes."""
    if data[:4] == JKS_MAGIC:
        return "JKS"
    if data[:4] == JCEKS_MAGIC:
        return "JCEKS"
    if data[:1] == b"\x30":
        return "PKCS#12"
    return ""


# The helper written into the connection's code. Standard library and cryptography; pyjks for JKS.
KEYSTORE_FILES = '''def keystore_files(path, password, alias=""):
    """The keystore's private key and certificate chain as two PEM files only you can read, removed
    when this Python ends: (certificate, key). PKCS#12, JKS or JCEKS, told by the file's first bytes."""
    import atexit
    import base64
    import os
    import shutil
    import tempfile

    if not os.path.isfile(path):
        named = sorted(k for k, v in os.environ.items() if v == path)
        raise FileNotFoundError(
            f"No keystore file at {path}" + (f" (from {', '.join(named)})" if named else "") + ". "
            "Choose it again here; where the code runs elsewhere (a function app), set its variable "
            "to the file's path there."
        )
    with open(path, "rb") as file:
        data = file.read()
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
        raise ValueError("The keystore's format is not known: it is not PKCS#12 (.p12, .pfx), JKS or JCEKS.")

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

# Trino's two ways to sign in (server/blade_templates.py): the user's password, or the keystore.
TRINO_BASIC = """import requests
import trino

user = "my_user"
verify = r"C:\\certs\\my-company-ca.pem"
trust_server_certificate = False

session = requests.Session()
session.verify = False if trust_server_certificate else verify
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

TRINO_KEYSTORE = f"""import os

import requests
import trino

user = "my_user"
keystore = r"C:\\certs\\my.keystore"
keystore_alias = ""  # the entry to use when the keystore holds more than one key
verify = r"C:\\certs\\my-company-ca.pem"
trust_server_certificate = False


{KEYSTORE_FILES}

session = requests.Session()
session.verify = False if trust_server_certificate else verify
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

SIGN_INS: tuple[tuple[str, str, str], ...] = (
    ("Username and password", "BasicAuthentication", TRINO_BASIC),
    ("Client certificate (keystore)", MARK, TRINO_KEYSTORE),
)
