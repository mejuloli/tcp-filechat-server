# TCP FileChat Server

Aplicação cliente-servidor TCP em Python, usando sockets e multithreading, desenvolvida para a disciplina de Redes de Computadores.

O projeto implementa:

- **Servidor TCP multithread** capaz de atender múltiplos clientes simultaneamente.
- **Chat bidirecional** entre servidor e clientes (broadcast).
- **Transferência de arquivos**, incluindo arquivos grandes (> 10 MB).
- **Verificação de integridade** dos arquivos via hash **SHA-256**.
- **Tratamento de erros**, como arquivo não encontrado.
- Implementação direta com **sockets TCP**, sem bibliotecas de alto nível que abstraiam a conexão.

---

## 🧱 Estrutura do projeto

```text
.
├── client.py        # Cliente TCP com menu interativo (chat, arquivo, sair)
├── server.py        # Servidor TCP multithread (uma thread por cliente)
├── protocol.py      # Funções auxiliares do protocolo (JSON + prefixo de tamanho)
├── server_files/    # Arquivos disponíveis para download no servidor
├── .gitignore
└── README.md
````

> A pasta `downloads/` será criada automaticamente pelo **client.py** quando algum arquivo for recebido.

---

## 🧩 Tecnologias utilizadas

* **Linguagem:** Python 3
* **Rede:** `socket` (TCP)
* **Concorrência:** `threading`
* **Hash:** `hashlib` (SHA-256)
* **Protocolo próprio** em cima de TCP, com cabeçalho JSON e prefixo de tamanho.

Nenhuma biblioteca externa é usada para esconder/manipular sockets de forma automática.

---

## 🚀 Como rodar o projeto

### 1. Pré-requisitos

* Python 3 instalado.
* Terminal / prompt de comando.
* Projeto clonado ou arquivos copiados para uma pasta local.

### 2. Preparar a pasta de arquivos do servidor

Na raiz do projeto, certifique-se de ter a pasta:

```text
server_files/
```

Coloque dentro dela os arquivos que o servidor poderá enviar, por exemplo:

* `teste.txt`
* `arquivo_grande.mp4` (algum arquivo > 10 MB para demonstração)
* etc.

### 3. Iniciar o servidor

No terminal, dentro da pasta do projeto, execute:

```bash
python server.py
# ou, no Windows:
py server.py
```

Você verá algo como:

```text
[*] Iniciando servidor TCP em 0.0.0.0:5000 ...
[OK] Servidor escutando em 0.0.0.0:5000
[CONSOLE] Digite mensagens para enviar a todos os clientes. Use /quit para encerrar o servidor.
```

Deixe esse terminal **aberto**: ele é o servidor.

> Tudo que você digitar nesse terminal (exceto `/quit`) será enviado como mensagem de chat para todos os clientes conectados.

### 4. Iniciar um cliente

Abra outro terminal na mesma pasta e execute:

```bash
python client.py
# ou:
py client.py
```

O cliente vai pedir:

* **IP do servidor** → aperte **Enter** para usar `127.0.0.1` (localhost).
* **Porta do servidor** → aperte **Enter** para usar `5000`.

Se tudo estiver certo, aparecerá:

```text
Conectado ao servidor 127.0.0.1:5000
```

E no servidor:

```text
[CONEXÃO] Cliente 1 conectado de 127.0.0.1:xxxxx.
```

---

## 🗣️ Menu do cliente

O cliente oferece um menu interativo:

```text
--- MENU ---
1 - Chat (enviar mensagem)
2 - Solicitar arquivo
3 - Sair
```

### 1. Chat (opção 1)

* Permite enviar mensagens de texto para o servidor.
* O servidor:

  * Exibe a mensagem no seu console.
  * Repassa (broadcast) a mensagem para todos os clientes conectados.
* No cliente, as mensagens chegam no formato:

```text
[CHAT - SERVIDOR] mensagem...
[CHAT - CLIENTE 1] mensagem...
```

### 2. Solicitar arquivo (opção 2)

* Solicita ao servidor um arquivo que esteja na pasta `server_files/`.
* Ao escolher essa opção, o cliente pergunta:

```text
Nome do arquivo no servidor:
```

Basta digitar exatamente o nome do arquivo, por exemplo:

```text
teste.txt
arquivo_grande.mp4
```

#### Comportamento:

* **Servidor**:

  * Verifica se o arquivo existe em `server_files/`.
  * Se existir:

    * Calcula o hash SHA-256 do conteúdo completo.
    * Envia um cabeçalho com:

      * `status = "OK"`
      * `filename`
      * `filesize`
      * `sha256`
    * Em seguida, envia o arquivo em blocos (suporta > 10 MB).
  * Se **não** existir:

    * Envia um cabeçalho com `status = "ERRO_ARQUIVO_NAO_ENCONTRADO"` e uma mensagem de erro.

* **Cliente**:

  * Se receber `status = "OK"`:

    * Cria a pasta `downloads/` (se ainda não existir).
    * Salva o arquivo em `downloads/<nome_arquivo>`.
    * Calcula o SHA-256 do arquivo recebido.
    * Compara com o hash enviado pelo servidor.
    * Informa se a integridade está **OK** ou se o arquivo foi corrompido.
  * Se receber status de erro:

    * Exibe a mensagem de erro na tela.

### 3. Sair (opção 3)

* Envia a requisição `SAIR` para o servidor.
* O servidor:

  * Envia uma mensagem `BYE`.
  * Fecha a conexão com aquele cliente.
* O cliente:

  * Fecha o socket.
  * Encerra a execução.

---

## 👥 Multithreading e múltiplos clientes

O servidor foi implementado como **multithread**:

* Cada conexão aceita gera uma **thread dedicada** (`handle_client`).
* É possível abrir **vários terminais** e rodar `client.py` em cada um.
* Todos os clientes:

  * Recebem as mensagens de chat (broadcast).
  * Podem solicitar arquivos ao mesmo tempo.

Para demonstrar isso:

1. Inicie o servidor.
2. Abra dois ou mais clientes.
3. Envie mensagens de chat de clientes diferentes.
4. Solicite arquivos de clientes diferentes.
5. Observe os logs do servidor e as mensagens de todos os clientes.

---

## 📡 Protocolo de aplicação (resumo)

### Cliente → Servidor (texto, por linha)

Os comandos enviados pelo cliente são strings de texto terminadas por `\n`:

* `SAIR`
* `ARQUIVO <Nome_Arquivo.ext>`
* `CHAT <Mensagem>`

### Servidor → Cliente (binário + JSON)

As mensagens do servidor para o cliente usam um formato fixo:

1. **4 bytes** com o tamanho do cabeçalho JSON em bytes (inteiro sem sinal, big-endian).
2. **Cabeçalho JSON** (UTF-8) com campos como:

   * `type`: `"CHAT"`, `"FILE_INFO"`, `"BYE"`, `"ERRO"`, etc.
   * Outros campos, dependendo do tipo.

Em alguns casos, após o cabeçalho, existe um **payload binário** (por exemplo, o conteúdo do arquivo).

#### Tipos principais

* **CHAT**

  * `type`: `"CHAT"`
  * `from`: `"SERVIDOR"` ou `"CLIENTE X"`
  * `message`: texto
  * Sem payload adicional.

* **FILE_INFO**

  * `type`: `"FILE_INFO"`
  * `status`: `"OK"` ou `"ERRO_ARQUIVO_NAO_ENCONTRADO"` (ou outro código de erro).
  * `filename`: nome do arquivo.
  * `filesize`: tamanho do arquivo em bytes (quando `status == "OK"`).
  * `sha256`: hash do arquivo em hexadecimal (quando `status == "OK"`).
  * `message`: mensagem explicativa em caso de erro.
  * Se `status == "OK"`:

    * Após o cabeçalho, o servidor envia **exatamente `filesize` bytes** com o conteúdo do arquivo.

* **BYE**

  * `type`: `"BYE"`
  * `message`: string com motivo do encerramento.
