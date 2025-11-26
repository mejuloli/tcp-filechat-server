# client.py
import socket
import threading
import os
import hashlib

from protocol import recv_header, recv_exact

# ===== eventos para sincronizar a thread do menu com a thread de recepção =====
waiting_for_file = threading.Event()
waiting_for_chat = threading.Event()

# ===== controle de operação de arquivo e fila de chats =====
pending_file_operation = False
pending_file_operation_lock = threading.Lock()

pending_chats = []  # lista de tuplas (origin, message)
pending_chats_lock = threading.Lock()

# evento para dizer que existem chats a serem mostrados depois do arquivo
chats_after_file = threading.Event()


def show_menu():
    menu = (
        "\n--- MENU ---\n1 - Chat (enviar mensagem)\n2 - Solicitar arquivo\n3 - Sair\n"
    )
    print(menu, end="")


def receive_loop(sock: socket.socket) -> None:
    """
    * thread que fica ouvindo o servidor e trata:
    - CHAT
    - FILE_INFO (com transferência de arquivo)
    - BYE
    """
    global pending_file_operation

    try:
        while True:
            try:
                header = recv_header(sock)
            except ConnectionError:
                print("\n[CLIENTE] Conexão encerrada pelo servidor.")
                break

            msg_type = header.get("type")

            # ===== mensagens de CHAT =====
            if msg_type == "CHAT":
                origin = header.get("from", "SERVIDOR")
                message = header.get("message", "")

                # verifica se há operação de arquivo pendente
                with pending_file_operation_lock:
                    suppress_chat = pending_file_operation

                if suppress_chat:
                    # guarda para mostrar depois do término da operação de arquivo
                    with pending_chats_lock:
                        pending_chats.append((origin, message))
                    # não imprime agora
                else:
                    # pode imprimir normalmente
                    print(f"\n[CHAT - {origin}] {message}")

                # avisa que pelo menos uma mensagem de chat chegou
                waiting_for_chat.set()

            # ===== informações de ARQUIVO + dados =====
            elif msg_type == "FILE_INFO":
                status = header.get("status")
                filename = header.get("filename", "arquivo_desconhecido")

                # caso de erro (arquivo não encontrado, etc.)
                if status != "OK":
                    message = header.get("message", "Erro ao receber arquivo.")
                    print(f"\n[ARQUIVO] Erro ao solicitar '{filename}': {message}")

                    # fim da operação de arquivo (mesmo com erro)
                    with pending_file_operation_lock:
                        pending_file_operation = False

                    # se tiver chats pendentes, marca para mostrar depois
                    with pending_chats_lock:
                        if pending_chats:
                            chats_after_file.set()

                    # sinaliza que terminou de tratar essa requisição de arquivo
                    waiting_for_file.set()
                    continue

                # ---- caso OK: segue com a transferência de arquivo ----
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

                # fim da operação de arquivo (sucesso ou falha de integridade)
                with pending_file_operation_lock:
                    pending_file_operation = False

                # se tiver chats pendentes, marca para mostrar DEPOIS
                with pending_chats_lock:
                    if pending_chats:
                        chats_after_file.set()

                # sinaliza para a thread do menu que terminou a operação de arquivo
                waiting_for_file.set()

            # ===== BYE: servidor encerrando conexão =====
            elif msg_type == "BYE":
                message = header.get("message", "Conexão encerrada.")
                print(f"\n[SERVER] {message}")
                break

            else:
                print(f"\n[MENSAGEM DESCONHECIDA] {header}")

    except Exception as e:
        print(f"\n[ERRO RECEIVE LOOP] {e}")
    finally:
        # garante que ninguém fique travado esperando se a conexão cair
        waiting_for_file.set()
        waiting_for_chat.set()
        print("[CLIENTE] Loop de recepção encerrado.")


def main():
    global pending_file_operation

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

    # ===== inicia thread de recepção =====
    t = threading.Thread(target=receive_loop, args=(sock,))
    t.start()

    try:
        while True:
            show_menu()
            opc = input("Escolha uma opção: ").strip()

            # ===== CHAT =====
            if opc == "1":
                msg = input("Digite sua mensagem de chat: ").strip()
                if msg:
                    # prepara para esperar uma possível resposta de chat
                    waiting_for_chat.clear()
                    line = f"CHAT {msg}\n"
                    sock.sendall(line.encode("utf-8"))
                    # espera até 2 segundos por alguma mensagem de chat
                    waiting_for_chat.wait(timeout=2.0)

            # ===== ARQUIVO =====
            elif opc == "2":
                filename = input("Nome do arquivo no servidor: ").strip()
                if filename:
                    # marca início de uma operação de arquivo (do pedido até o fim do tratamento)
                    with pending_file_operation_lock:
                        pending_file_operation = True

                    waiting_for_file.clear()
                    line = f"ARQUIVO {filename}\n"
                    sock.sendall(line.encode("utf-8"))
                    print("[CLIENTE] Aguardando transferência de arquivo terminar...")
                    # bloqueia até a thread de recepção sinalizar que acabou
                    waiting_for_file.wait()
                    print("[CLIENTE] Operação de arquivo finalizada.")

                    # só agora, DEPOIS de finalizar, mostra os chats pendentes, se houver
                    if chats_after_file.is_set():
                        with pending_chats_lock:
                            if pending_chats:
                                print(
                                    "\n[CHAT] Mensagens recebidas enquanto o arquivo era transferido:"
                                )
                                for origin, message in pending_chats:
                                    print(f"[CHAT - {origin}] {message}")
                                pending_chats.clear()
                        chats_after_file.clear()

            # ===== SAIR =====
            elif opc == "3":
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

        # espera thread terminar para não imprimir durante shutdown
        t.join()

        print("[CLIENTE] Conexão fechada. Fim.")


if __name__ == "__main__":
    main()
