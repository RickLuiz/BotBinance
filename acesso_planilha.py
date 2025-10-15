import time
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Nome do arquivo JSON da chave
SERVICE_ACCOUNT_FILE = 'chave.json'

# Escopo para acessar o Google Sheets (e Drive, se necessário)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# ID da planilha (disponível na URL da sua planilha)
SPREADSHEET_ID = '1DPOZRTIc-CSdlSsWGkbutTkniT1WnKMNm2EcN7JIHaM'

# Intervalo de dados que você deseja ler (ex.: "A1:D10")
RANGE_NAME = 'Página1!B2:L2'  # Altere o intervalo para a linha com os valores que você quer usar.


class AcessoPlanilha:

    def __init__(self):
        # Definindo as variáveis de instância
        self.on_off = None
        self.estrategia = None
        self.saldo_a_usar = None
        self.volume_minimo = None
        self.intervalo_analise = None
        self.limite_criptos = None
        self.dias_volatilidade = None
        self.horas_volatilidade = None
        self.limite_posicao = None
        self.lucro_venda = None
        self.modo_teste = None

    # Função para obter as variáveis da planilha
    def get_config_from_spreadsheet(self):
        try:
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            service = build('sheets', 'v4', credentials=credentials)

            # Lê os dados da planilha
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
            rows = result.get('values', [])

            # Verificar se há dados e atribuí-los às variáveis
            if rows:
                linha = rows[0]
                self.on_off = linha[0] == "Ligado" if len(linha) > 0 else None
                self.estrategia = linha[1] if len(linha) > 1 else None
                self.saldo_a_usar = linha[2] if len(linha) > 2 else None
                self.volume_minimo = linha[3] if len(linha) > 3 else None
                self.intervalo_analise = linha[4] if len(linha) > 4 else None
                self.limite_criptos = linha[5] if len(linha) > 5 else None
                self.dias_volatilidade = int(float(linha[6].replace(",", "."))) if len(linha) > 6 and linha[6] else None
                self.horas_volatilidade = float(linha[10].replace(",", ".")) if len(linha) > 10 and linha[10] else None
                self.limite_posicao = float(linha[7].replace(",", ".")) if len(linha) > 7 and linha[7] else None
                self.lucro_venda = linha[8] if len(linha) > 8 else None
                self.modo_teste = linha[9] == "Ligado" if len(linha) > 9 else None
                return {
                    "on_off": self.on_off,
                    "estrategia": self.estrategia,
                    "saldo_a_usar": self.saldo_a_usar,
                    "volume_minimo": self.volume_minimo,
                    "intervalo_analise": self.intervalo_analise,
                    "limite_criptos": self.limite_criptos,
                    "dias_volatilidade": self.dias_volatilidade,
                    "horas_volatilidade": self.horas_volatilidade,
                    "limite_posicao": self.limite_posicao,
                    "lucro_venda": self.lucro_venda,
                    "modo_teste": self.modo_teste,
                }
            else:
                print("Nenhum dado encontrado no intervalo especificado.")
                return None

        except HttpError as e:
            print(f"Erro ao acessar a planilha: {e}")
            self.append_message("Erro ao acessar a planilha: operação ignorada.")
            return None

    # Função para atualizar uma célula na planilha
    def update_error_message(self, message):
        try:
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            service = build('sheets', 'v4', credentials=credentials)
            sheet = service.spreadsheets()

            range_ = 'Página1!M2'
            values = [[message]]

            body = {'values': values}
            sheet.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_,
                valueInputOption="RAW",
                body=body
            ).execute()
            #print("Mensagem de erro atualizada com sucesso.")

        except HttpError as e:
             pass#print(f"Erro ao atualizar a mensagem de erro: {e}")
        
# Lista de criptos que saírão de operação
    def get_blacklist_from_spreadsheet(self):
        """
        Lê a lista de criptomoedas na coluna N da guia 'Página1' e retorna como uma lista.
        """
        try:
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            service = build('sheets', 'v4', credentials=credentials)

            # Lê a coluna N da guia "Página1", começando da linha 2
            range_name = 'Página1!N2:N'
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
            rows = result.get('values', [])

            # Retornar os valores como uma lista (remover valores vazios)
            blacklist = [row[0] for row in rows if row]
            return blacklist

        except HttpError as e:
            print(f"Erro ao acessar a planilha para obter a blacklist: {e}")
            return []

        


    # Função para inserir log na planilha
    def append_message(self, message):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
                service = build('sheets', 'v4', credentials=credentials)
                sheet = service.spreadsheets()

                range_ = 'Página2!A:A'
                result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_).execute()
                rows = result.get('values', [])
                next_row = len(rows) + 1
                next_range = f'Página2!A{next_row}'

                values = [[message]]
                body = {'values': values}
                sheet.values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=next_range,
                    valueInputOption="RAW",
                    body=body
                ).execute()
                #print("Mensagem de log adicionada com sucesso.")
                break

            except HttpError as e:
                #print(f"Tentativa {attempt + 1} falhou ao adicionar mensagem de log: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    pass  # print("Falha ao adicionar mensagem de log após várias tentativas.")

    # Função para apagar log da planilha
    def clear_column_a(self):
        try:
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            service = build('sheets', 'v4', credentials=credentials)
            sheet = service.spreadsheets()

            range_ = 'Página2!A:A'
            sheet.values().clear(spreadsheetId=SPREADSHEET_ID, range=range_).execute()
           # print("Coluna A limpa com sucesso.")

        except HttpError as e:
            pass# print(f"Erro ao limpar a coluna A: {e}")


# Criando uma instância da classe
acesso = AcessoPlanilha()

# Chamando o método para obter os dados
config = acesso.get_config_from_spreadsheet()

# Imprimindo os dados obtidos
if config:
    print("Parâmetros atualizados:") #, config)
