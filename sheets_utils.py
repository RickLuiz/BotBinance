import gspread
from google.oauth2.service_account import Credentials

# Escopos de acesso (leitura e escrita)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Arquivo da chave da conta de serviço JSON
SERVICE_ACCOUNT_FILE = 'chave.json'  # atualize se seu arquivo tem outro nome

# Autenticação e cliente gspread
creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
gc = gspread.authorize(creds)

# Seu ID da planilha (deve ser passado para as funções)
# Pode ser lido direto do main.py, aqui só usamos como parâmetro

def get_sheet_data(spreadsheet_id: str, worksheet_name: str = 'Sheet1'):
    """
    Retorna os dados da worksheet como lista de dicionários.
    Cada dicionário representa uma linha, com chaves pelos cabeçalhos.
    """
    sh = gc.open_by_key(spreadsheet_id)
    worksheet = sh.worksheet(worksheet_name)
    records = worksheet.get_all_records()
    return records

def update_sheet_data(spreadsheet_id: str, updates: list[dict], worksheet_name: str = 'Sheet1'):
    """
    Atualiza linhas na worksheet baseado no índice da linha.
    'updates' deve ser uma lista de dicionários com o formato:
    {
        'row': int,        # índice da linha (começando em 2, porque 1 são cabeçalhos)
        'values': dict     # chave-valor para colunas e valores a atualizar
    }

    Exemplo:
    [
        {'row': 2, 'values': {'Nome': 'Henrique', 'Idade': 40}},
        {'row': 5, 'values': {'Nome': 'Maria', 'Idade': 30}},
    ]
    """
    sh = gc.open_by_key(spreadsheet_id)
    worksheet = sh.worksheet(worksheet_name)

    # Pega os cabeçalhos da planilha para mapear colunas
    headers = worksheet.row_values(1)

    for update in updates:
        row_number = update['row']
        values = update['values']

        for key, val in values.items():
            if key in headers:
                col_number = headers.index(key) + 1
                worksheet.update_cell(row_number, col_number, val)
            else:
                raise ValueError(f"Coluna '{key}' não encontrada na planilha.")

    return True
