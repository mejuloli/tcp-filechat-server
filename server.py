# server.py
import socket
import threading
import os
import hashlib
import sys

from protocol import send_header

HOST = "0.0.0.0"
PORT = 5000  # porta > 1024

# ===== diretório base do projeto (onde está o server.py) =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ===== pasta onde ficarão os arquivos que o servidor pode enviar aos clientes =====
FILES_DIR = os.path.join(BASE_DIR, "server_files")
os.makedirs(FILES_DIR, exist_ok=True)

# ===== lista global de clientes conectados =====
# cada item é um dict: {"id": int, "socket": socket, "send_lock": Lock, "address": (ip, port)}
clients = []
clients_lock = threading.Lock()

# ===== controle de IDs de clientes =====
_client_id_counter = 0
client_id_lock = threading.Lock()

# ===== evento global para sinalizar desligamento do servidor =====
shutdown_event = threading.Event()


def next_client_id() -> int:
    global _client_id_counter
    with client_id_lock:
        _client_id_counter += 1
        return _client_id_counter


def broadcast_chat(message: str, from_name: str = "SERVIDOR", exclude_id=None) -> None:
    """
    - envia uma mensagem de chat para todos os clientes conectados.
    - usa o protocolo: cabeçalho JSON com type="CHAT".
    - se exclude_id for fornecido, não envia para esse cliente.
    """
    header = {
        "type": "CHAT",
        "from": from_name,
        "message": message,
    }
    with clients_lock:
        dead_clients = []
        for client in clients:
            # se for para excluir um cliente específico, pula ele
            if exclude_id is not None and client.get("id") == exclude_id:
                continue

            conn = client["socket"]
            lock = client["send_lock"]
            try:
                with lock:
                    send_header(conn, header)
            except Exception:
                # ===== marca para remoção (cliente desconectou) =====
                dead_clients.append(client)

        # ===== remove clientes mortos =====
        for c in dead_clients:
            try:
                c["socket"].close()
            except Exception:
                pass
            clients.remove(c)


def shutdown_all_clients(reason: str) -> None:
    """
    Envia BYE para todos os clientes ainda conectados e fecha os sockets.
    """
    header = {"type": "BYE", "message": reason}

    with clients_lock:
        # primeiro tenta avisar todo mundo
        for client in clients:
            conn = client["socket"]
            lock = client["send_lock"]
            try:
                with lock:
                    send_header(conn, header)
            except Exception:
                # se falhar, segue em frente
                pass

        # depois fecha os sockets e limpa a lista
        for client in clients:
            try:
                client["socket"].close()
            except Exception:
                pass

        clients.clear()


def handle_file_request(client_info: dict, filename: str) -> None:
    """
    - trata requisição de ARQUIVO.
    - envia cabeçalho FILE_INFO + dados do arquivo (se existir).
    """
    conn = client_info["socket"]
    send_lock = client_info["send_lock"]

    # ==== verifica se o arquivo existe =====
    file_path = os.path.join(FILES_DIR, filename)

    if not os.path.isfile(file_path):
        header = {
            "type": "FILE_INFO",
            "status": "ERRO_ARQUIVO_NAO_ENCONTRADO",
            "filename": filename,
            "message": "Arquivo não encontrado no servidor.",
        }
        with send_lock:
            send_header(conn, header)
        print(
            f"[ARQUIVO] Cliente {client_info['id']}: arquivo '{filename}' NÃO encontrado."
        )
        return

    # ===== calcula tamanho e hash SHA-256 do arquivo =====
    filesize = os.path.getsize(file_path)
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1024 * 64)
            if not chunk:
                break
            sha256.update(chunk)
    file_hash = sha256.hexdigest()

    header = {
        "type": "FILE_INFO",
        "status": "OK",
        "filename": os.path.basename(filename),
        "filesize": filesize,
        "sha256": file_hash,
    }

    print(
        f"[ARQUIVO] Enviando '{filename}' ({filesize} bytes) para cliente {client_info['id']}."
    )

    # ===== envia cabeçalho + o arquivo inteiro sob um único lock (para não intercalar com chat) =====
    with send_lock:
        send_header(conn, header)
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 64)
                if not chunk:
                    break
                conn.sendall(chunk)

    print(
        f"[ARQUIVO] Envio do arquivo '{filename}' para cliente {client_info['id']} concluído."
    )


def handle_client(conn: socket.socket, addr) -> None:
    """
    - thread responsável por um cliente.
    - lê comandos de texto (SAIR, CHAT, ARQUIVO) via linhas.
    - usa protocolo binário para resposta (chat/file/etc).
    """
    client_id = next_client_id()
    addr_str = f"{addr[0]}:{addr[1]}"

    client_info = {
        "id": client_id,
        "socket": conn,
        "send_lock": threading.Lock(),
        "address": addr,
    }

    with clients_lock:
        clients.append(client_info)

    print(f"[CONEXÃO] Cliente {client_id} conectado de {addr_str}.")

    # ===== lê comandos de texto linha a linha =====
    # ===== apenas lê. escrita é feita com send_lock =====
    conn_file = conn.makefile("r", encoding="utf-8", newline="\n")

    try:
        while True:
            if shutdown_event.is_set():
                # servidor em desligamento: encerra educadamente
                print(
                    f"[INFO] Encerrando conexão com cliente {client_id} por shutdown."
                )
                header = {
                    "type": "BYE",
                    "message": "Servidor está sendo encerrado.",
                }
                with client_info["send_lock"]:
                    send_header(conn, header)
                break

            line = conn_file.readline()
            if not line:
                print(f"[DESCONECTADO] Cliente {client_id} fechou a conexão.")
                break

            line = line.strip()
            if not line:
                continue

            parts = line.split(" ", 1)
            command = parts[0].upper()

            if command == "SAIR":
                print(f"[COMANDO] Cliente {client_id} pediu para sair.")
                # ===== envia cabeçalho BYE =====
                header = {
                    "type": "BYE",
                    "message": "Conexão encerrada a pedido do cliente.",
                }
                with client_info["send_lock"]:
                    send_header(conn, header)
                break

            elif command == "CHAT":
                if len(parts) == 2:
                    message = parts[1]
                else:
                    message = ""
                print(f"[CHAT] De cliente {client_id} ({addr_str}): {message}")
                # ===== repassa para todos os outros clientes, exceto quem enviou =====
                broadcast_chat(
                    message,
                    from_name=f"CLIENTE {client_id}",
                    exclude_id=client_id,
                )

            elif command == "ARQUIVO":
                if len(parts) != 2 or not parts[1]:
                    print(f"[ERRO] Cliente {client_id} enviou ARQUIVO sem nome.")
                    header = {
                        "type": "FILE_INFO",
                        "status": "ERRO",
                        "filename": "",
                        "message": "Nome de arquivo não especificado.",
                    }
                    with client_info["send_lock"]:
                        send_header(conn, header)
                else:
                    filename = parts[1].strip()
                    handle_file_request(client_info, filename)

            else:
                print(f"[ERRO] Cliente {client_id} enviou comando desconhecido: {line}")
                # ===== envia aviso de erro genérico =====
                header = {
                    "type": "ERRO",
                    "message": f"Comando desconhecido: {command}",
                }
                with client_info["send_lock"]:
                    send_header(conn, header)

    except Exception as e:
        print(f"[EXCEÇÃO] Erro com cliente {client_id}: {e}")

    finally:
        conn_file.close()
        conn.close()
        with clients_lock:
            if client_info in clients:
                clients.remove(client_info)
        print(f"[FIM] Thread do cliente {client_id} encerrada.")


def server_console() -> None:
    # ===== thread que lê do console do servidor e envia chat para todos os clientes. =====
    print(
        "[CONSOLE] Digite mensagens para enviar a todos os clientes. Use /quit para encerrar o servidor."
    )
    for line in sys.stdin:
        msg = line.rstrip("\n")
        if not msg:
            continue
        if msg.strip().lower() == "/quit":
            print("[CONSOLE] Solicitação de encerramento do servidor recebida.")
            # sinaliza para o loop principal encerrar
            shutdown_event.set()
            # avisa os clientes via chat
            broadcast_chat(
                "Servidor será encerrado pelo administrador.", from_name="SERVIDOR"
            )
            break
        broadcast_chat(msg, from_name="SERVIDOR")


def main():
    print(f"[*] Iniciando servidor TCP em {HOST}:{PORT} ...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        # timeout para poder checar o shutdown_event periodicamente
        s.settimeout(1.0)
        print(f"[OK] Servidor escutando em {HOST}:{PORT}")

        # ===== thread de console para chat do servidor =====
        console_thread = threading.Thread(target=server_console, daemon=True)
        console_thread.start()

        try:
            while not shutdown_event.is_set():
                try:
                    conn, addr = s.accept()
                except socket.timeout:
                    continue

                t = threading.Thread(
                    target=handle_client, args=(conn, addr), daemon=True
                )
                t.start()
        except KeyboardInterrupt:
            print("\n[ENCERRANDO] Servidor interrompido por KeyboardInterrupt.")
            shutdown_event.set()
        finally:
            print("[ENCERRANDO] Fechando conexões com clientes...")
            shutdown_all_clients("Servidor está sendo encerrado.")
            print("[FIM] Servidor encerrado.")


if __name__ == "__main__":
    main()
