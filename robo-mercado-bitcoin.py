import requests
import os
from decouple import config

# Carregar credenciais do arquivo .env
API_TOKEN_ID = config('USERNAME')
API_TOKEN_SECRET = config('PASSWORD')

# URL base da API
BASE_URL = "https://api.mercadobitcoin.net/api/v4"

# Endpoint para autenticação (acessar a chave)
auth_url = f"{BASE_URL}/authorize"
auth_data = {
    "login": API_TOKEN_ID,  # Mudamos de 'username' para 'login'
    "password": API_TOKEN_SECRET
}

# Fazendo a autenticação
response = requests.post(auth_url, data=auth_data)

# Verificando o sucesso da autenticação
if response.status_code == 200:
    auth_token = response.json().get("access_token")
    print("Autenticação bem-sucedida!")
else:
    print(f"Erro na autenticação: {response.status_code} - {response.text}")
    exit()

# Definir o cabeçalho de autorização
headers = {
    'Authorization': f'Bearer {auth_token}'
}

# Endpoint para consultar o preço do Bitcoin
ticker_url = f"{BASE_URL}/ticker"

# Consultando o preço do Bitcoin
response = requests.get(ticker_url, headers=headers)

# Verificando a resposta
if response.status_code == 200:
    data = response.json()
    print("Preço do Bitcoin (BRL):", data['ticker']['last'])
else:
    print(f"Erro ao consultar o preço: {response.status_code} - {response.text}")
