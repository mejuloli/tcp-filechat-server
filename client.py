import socket
import threading
import os
import hashlib
from protocol import (
    send_header,
    recv_header,
    recv_exact,
)


def receive_loop(sock: socket.socket) -> None:
    """
    * thread que fica ouvindo o servidor e trata:
    - CHAT
    - FILE_INFO (com transferência de arquivo)
    - BYE
    """
    try:
        while True:
            try:
                header = recv_header(sock)
            except ConnectionError:
                print("\n[CLIENTE] Conexão encerrada pelo servidor.")
                break

            msg_type = header.get("type")

            if msg_type == "CHAT":
                origin = header.get("from", "SERVIDOR")
                message = header.get("message", "")
                print(f"\n[CHAT - {origin}] {message}")

            elif msg_type == "FILE_INFO":
                status = header.get("status")
                filename = header.get("filename", "arquivo_desconhecido")

                if status != "OK":
                    message = header.get("message", "Erro ao receber arquivo.")
                    print(f"\n[ARQUIVO] Erro ao solicitar '{filename}': {message}")
                    continue

                filesize = int(header.get("filesize", 0))
                expected_hash = header.get("sha256", "")

                save_dir = os.path.join(os.getcwd(), "downloads")
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, filename)

                print(f"\n[ARQUIVO] Recebendo '{filename}' ({filesize} bytes)...")
                print(f"[ARQUIVO] Salvando em: {save_path}")

                remaining = filesize
                hasher = hashlib.sha256()

                with open(save_path, "wb") as f:
                    while remaining > 0:
                        chunk_size = min(1024 * 64, remaining)
                        chunk = recv_exact(sock, chunk_size)
                        f.write(chunk)
                        hasher.update(chunk)
                        remaining -= len(chunk)

                received_hash = hasher.hexdigest()
                print(f"[ARQUIVO] Hash SHA-256 esperado: {expected_hash}")
                print(f"[ARQUIVO] Hash SHA-256 recebido: {received_hash}")

                if received_hash == expected_hash:
                    print("[ARQUIVO] Arquivo recebido com SUCESSO (integridade OK).")
                else:
                    print("[ARQUIVO] ERRO: Arquivo corrompido (hash diferente).")

            elif msg_type == "BYE":
                message = header.get("message", "Conexão encerrada.")
                print(f"\n[SERVER] {message}")
                break

            else:
                print(f"\n[MENSAGEM DESCONHECIDA] {header}")

    except Exception as e:
        print(f"\n[ERRO RECEIVE LOOP] {e}")
    finally:
        print("[CLIENTE] Loop de recepção encerrado.")


def main():
    print("=== Cliente TCP ===")
    host = input("IP do servidor [127.0.0.1]: ").strip() or "127.0.0.1"
    port_str = input("Porta do servidor [5000]: ").strip() or "5000"

    try:
        port = int(port_str)
    except ValueError:
        print("Porta inválida.")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((host, port))
    except Exception as e:
        print(f"Não foi possível conectar ao servidor: {e}")
        return

    print(f"Conectado ao servidor {host}:{port}")

    # ===== inicia a thread de recepção =====
    t = threading.Thread(target=receive_loop, args=(sock,), daemon=True)
    t.start()

    try:
        while True:
            print("\n--- MENU ---")
            print("1 - Chat (enviar mensagem)")
            print("2 - Solicitar arquivo")
            print("3 - Sair")
            opc = input("Escolha uma opção: ").strip()

            if opc == "1":
                msg = input("Digite sua mensagem de chat: ").strip()
                if msg:
                    # ===== envia comando de texto: CHAT <mensagem>\n ====
                    line = f"CHAT {msg}\n"
                    sock.sendall(line.encode("utf-8"))

            elif opc == "2":
                filename = input("Nome do arquivo no servidor: ").strip()
                if filename:
                    line = f"ARQUIVO {filename}\n"
                    sock.sendall(line.encode("utf-8"))

            elif opc == "3":
                # ===== envia SAIR e encerra o cliente =====
                sock.sendall(b"SAIR\n")
                print("Encerrando cliente...")
                break

            else:
                print("Opção inválida. Tente novamente.")

    except KeyboardInterrupt:
        print("\n[CLIENTE] Interrompido pelo usuário.")
    finally:
        try:
            sock.close()
        except Exception:
            pass
        print("[CLIENTE] Conexão fechada. Fim.")


if __name__ == "__main__":
    main()
