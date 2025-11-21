import json
import struct

# ===== cabeçalho: 4 bytes (tamanho do JSON) + JSON (UTF-8) =====
_HEADER_STRUCT = struct.Struct("!I")


def recv_exact(sock, n: int) -> bytes:
    """
    * lê exatamente n bytes do socket.
    * levanta ConnectionError se a conexão fechar antes.
    """
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Conexão encerrada enquanto recebia dados.")
        data.extend(chunk)
    return bytes(data)


def send_header(sock, header: dict) -> None:
    """
    ===== envia apenas o cabeçalho JSON com prefixo de tamanho. =====
    """
    header_bytes = json.dumps(header).encode("utf-8")
    sock.sendall(_HEADER_STRUCT.pack(len(header_bytes)))
    sock.sendall(header_bytes)


def recv_header(sock) -> dict:
    """
    ===== recebe o cabeçalho JSON (com prefixo de tamanho) e retorna como dict. =====
    """
    length_bytes = recv_exact(sock, _HEADER_STRUCT.size)
    (length,) = _HEADER_STRUCT.unpack(length_bytes)
    header_bytes = recv_exact(sock, length)
    return json.loads(header_bytes.decode("utf-8"))
