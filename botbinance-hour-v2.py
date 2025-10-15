import time
import numpy as np
import math
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
import os
from send_email import send_email
from acesso_planilha import AcessoPlanilha
from datetime import datetime
import concurrent.futures

acesso = AcessoPlanilha()
config = acesso.get_config_from_spreadsheet()

# Carregar variáveis de ambiente do .env
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
client = Client(API_KEY, API_SECRET)

# Função para obter o saldo
def get_balance(asset):
    try:
        # Obter informações de saldo para o ativo especificado
        balance = client.get_asset_balance(asset=asset)
        
        # Garantir que os dados retornados estão completos
        if not balance:
            raise ValueError(f"Nenhuma informação de saldo retornada para o ativo {asset}.")

        free_balance = float(balance['free'])
        locked_balance = float(balance['locked'])

        # Log detalhado
       # print(f"Dados retornados pela API para {asset}: {balance}")
        #print(f"Saldo livre: {free_balance:.8f}, Saldo bloqueado: {locked_balance:.8f}")

        return free_balance
    except BinanceAPIException as e:
        print(f"Erro ao obter saldo para {asset} via API: {e}")
        return 0.0
    except ValueError as ve:
        print(ve)
        return 0.0
    except Exception as e:
        print(f"Erro inesperado ao obter saldo para {asset}: {e}")
        return 0.0


# Função para obter todos os ativos na carteira com saldo livre
def get_wallet_assets(min_balance=0.0):
    """
    Retorna um dicionário com os ativos na carteira e seus saldos livres.
    Exclui USDT e BRL por padrão.
    """
    try:
        balances = client.get_account()['balances']
        wallet = {}
        for balance in balances:
            asset = balance['asset']
            free_balance = float(balance['free'])
            if asset not in ["USDT", "BRL"] and free_balance > min_balance:
                wallet[asset] = free_balance
        return wallet
    except BinanceAPIException as e:
        print(f"Erro ao obter ativos da carteira: {e}")
        return {}

# Calcular volatilidade histórica
def get_historical_volatility(symbol, days):
    try:
        klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1DAY, f"{days} days ago UTC")
        closes = [float(kline[4]) for kline in klines]
        if len(closes) < 2:
            return None
        daily_returns = np.diff(closes) / closes[:-1]
        return np.std(daily_returns)
    except Exception as e:
        print(f"Erro ao calcular volatilidade para {symbol.replace('USDT', '')}: {e}")
        return None

# Calcula as Bandas de Bollinger
def calculate_bollinger_bands(symbol, interval='1h', hours=24):
    """
    Calcula as Bandas de Bollinger para um ativo com base no intervalo desejado.
    
    :param symbol: Símbolo da criptomoeda, e.g., 'BTCUSDT'.
    :param interval: Intervalo das velas (e.g., '1h', '4h'). Default é '1h'.
    :param hours: Número de horas para análise. Default é 24.
    :return: Preço atual, banda inferior, banda superior.
    """
    # Converte horas para o formato correto para klines
    start_time = f"{hours} hours ago UTC"
    
    # Obter os dados de candles
    klines = client.get_historical_klines(symbol, interval, start_time)
    
    # Extrair preços de fechamento
    closes = [float(kline[4]) for kline in klines]
    
    # Garantir que haja dados suficientes para o cálculo
    if len(closes) < 2:
        raise ValueError("Dados insuficientes para calcular as Bandas de Bollinger.")
    
    # Calcular média móvel simples (SMA) e desvio padrão
    sma = sum(closes) / len(closes)
    std_dev = np.std(closes)
    
    # Calcular bandas superior e inferior
    upper_band = sma + (2 * std_dev)
    lower_band = sma - (2 * std_dev)
    
    # Retorna o preço atual, a banda inferior e a banda superior
    return closes[-1], lower_band, upper_band

# Calcula o RSI
def calculate_rsi(symbol, interval='1h', hours=14):
    """
    Calcula o Índice de Força Relativa (RSI) para um ativo em um intervalo específico.

    :param symbol: Símbolo da criptomoeda, e.g., 'BTCUSDT'.
    :param interval: Intervalo das velas (e.g., '1h', '4h'). Default é '1h'.
    :param hours: Número de horas para análise. Default é 14.
    :return: RSI calculado.
    """
    # Converter horas para o formato esperado pela API Binance
    start_time = f"{hours} hours ago UTC"
    
    # Obter os dados de candles
    klines = client.get_historical_klines(symbol, interval, start_time)
    
    # Extrair preços de fechamento
    closes = [float(kline[4]) for kline in klines]
    
    # Garantir que há dados suficientes para calcular o RSI
    if len(closes) < 2:
        raise ValueError("Dados insuficientes para calcular o RSI.")
    
    # Calcular os deltas entre fechamentos consecutivos
    deltas = np.diff(closes)
    
    # Separar ganhos e perdas
    gain = np.mean([delta for delta in deltas if delta > 0]) if deltas.any() else 0
    loss = abs(np.mean([delta for delta in deltas if delta < 0])) if deltas.any() else 0
    
    # Calcular o índice de força relativa (RSI)
    rs = gain / loss if loss != 0 else 0
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

# Calcula a média móvel
def get_moving_averages(symbol, interval='1h', hours=20):
    """
    Calcula a média móvel simples (SMA) para um ativo em um intervalo específico.

    :param symbol: Símbolo da criptomoeda, e.g., 'BTCUSDT'.
    :param interval: Intervalo das velas (e.g., '1h', '4h'). Default é '1h'.
    :param hours: Número de horas para análise. Default é 20.
    :return: True se o preço atual for maior que a média móvel.
    """
    # Converter horas para o formato esperado pela API Binance
    start_time = f"{hours} hours ago UTC"
    
    # Obter os dados de candles
    klines = client.get_historical_klines(symbol, interval, start_time)
    
    # Extrair preços de fechamento
    closes = [float(kline[4]) for kline in klines]
    
    # Garantir que há dados suficientes para calcular a média móvel
    if len(closes) < 2:
        raise ValueError("Dados insuficientes para calcular a média móvel.")
    
    # Calcular a média móvel simples (SMA)
    sma = sum(closes) / len(closes)
    
    return closes[-1] > sma  # Retorna True se preço atual > média



# Função para calcular volatilidade, RSI e médias móveis em paralelo
def process_ticker(ticker, min_volume, wallet_assets, hours):
    try:
        symbol = ticker['symbol']
        volume = float(ticker['quoteVolume'])
        
        # Filtrar ativos com volume mínimo e que são par USDT
        if symbol.endswith('USDT') and volume >= min_volume:
            asset = symbol.replace('USDT', '')  # Remove 'USDT' para obter o ativo
            
            # Verificar se o ativo não está na carteira com saldo menor que 0.1
            if asset not in wallet_assets or wallet_assets[asset] < 0.1:
                # Calcular volatilidade
                volatility = get_historical_volatility(symbol, hours=hours)
                if volatility is not None:
                    # cálculo de médias móveis e RSI
                    if get_moving_averages(symbol) and calculate_rsi(symbol) < 70:
                        return {'symbol': symbol, 'volatility': volatility, 'volume': volume}

                    # Retornar o ativo com base apenas na volatilidade e volume
                    return {'symbol': symbol, 'volatility': volatility, 'volume': volume}
    except Exception as e:
        print(f"Erro ao processar o ticker {symbol}: {e}")
    return None



# Obter as criptos mais voláteis
def get_top_volatile_cryptos(limit=int(config['limite_criptos']), hours=int(config['horas_volatilidade']), min_volume=float(config['volume_minimo'].replace(',', '.'))):
    try:
        # Obter todos os tickers da Binance
        tickers = client.get_ticker()
        wallet_assets = get_wallet_assets(min_balance=0.1)  # Pegando os ativos da carteira com saldo >= 0.1
        
        # Processar os tickers em paralelo
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(process_ticker, ticker, min_volume, wallet_assets, hours) for ticker in tickers]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # Filtrar resultados válidos (não None)
        volatility_data = [result for result in results if result is not None]
        
        # Ordenar por volatilidade e retornar os top N
        top_volatile = sorted(volatility_data, key=lambda x: x['volatility'], reverse=True)
        return top_volatile[:limit]
        
    except Exception as e:
        print(f"Erro ao obter criptos mais voláteis: {e}")
        return []

# Função para calcular a volatilidade histórica
def get_historical_volatility(symbol, hours):
    try:
        # Certificando-se de que 'days' seja usado corretamente aqui
        klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, f"{hours} hour ago UTC")
        
        # Extrair preços de fechamento dos dados históricos
        closes = [float(kline[4]) for kline in klines]  # kline[4] é o preço de fechamento

        # Se não houver dados suficientes, retornar None
        if len(closes) < 2:
            #print(f"Dados insuficientes para calcular volatilidade para {symbol}")
            return None

        # Calcular os retornos diários (preço de fechamento hoje / preço de fechamento anterior - 1)
        returns = [closes[i+1] / closes[i] - 1 for i in range(len(closes) - 1)]

        # Calcular a volatilidade como o desvio padrão dos retornos diários
        volatility = np.std(returns)

        # Retornar a volatilidade
        return volatility

    except Exception as e:
        print(f"Erro ao calcular volatilidade para {symbol}: {e}")
        return None   

# Definindo a função get_order_history
def get_order_history(symbol, limit=100, from_id=None):
    try:
        orders = []
        while True:
            params = {'symbol': symbol, 'limit': limit}
            if from_id:
                params['fromId'] = from_id

            response = client.get_all_orders(**params)
            
            if not response:
                break

            orders.extend(response)
            from_id = response[-1]['orderId']

            if len(response) < limit:
                break
        
        return orders
    
    except BinanceAPIException as e:
        print(f"Erro ao recuperar o histórico de ordens para {symbol}: {e}")
        return []   

# Obter o valor mínimo de notional diretamente da API
def get_min_notional(symbol):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'MIN_NOTIONAL':
                return float(f['minNotional'])
        return 0.0
    except BinanceAPIException as e:
        print(f"Erro ao obter o mínimo notional para {symbol}: {e}")
        return 0.0

# Função para ajustar a quantidade pelo stepSize
def adjust_quantity(symbol, quantity):
    try:
        # Obtém as informações do símbolo
        symbol_info = client.get_symbol_info(symbol)
        
        # Encontra o filtro LOT_SIZE
        lot_size_filter = next(f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE')
        
        # Obtém o stepSize (precisão)
        step_size = float(lot_size_filter['stepSize'])
        
        # Calcula o número de casas decimais permitido pelo stepSize
        decimals = int(-math.log10(step_size))
        
        # Ajusta a quantidade para o múltiplo válido e formata com a precisão correta
        adjusted_quantity = math.floor(quantity / step_size) * step_size
        adjusted_quantity = round(adjusted_quantity, decimals)
        
        return adjusted_quantity
    except Exception as e:
        print(f"Erro ao ajustar quantidade para {symbol}: {e}")
        return quantity 

# Função para realizar a compra
def buy_crypto(symbol, quantity):
    try:
        if config['modo_teste'] == True:
            message = f"[TEST MODE] Compra simulada: {symbol.replace('USDT', '')} - Quantidade: {quantity:.6f}"
            send_email("Compra Simulada", message)
            print(message)
            return {"status": "TEST", "symbol": symbol, "quantity": quantity}

        # Ajusta a quantidade conforme a precisão exigida
        quantity = adjust_quantity(symbol, quantity)

        # Obter as informações do símbolo
        info = client.get_symbol_info(symbol)
        lot_size_filter = next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')
        min_qty = float(lot_size_filter['minQty'])

        # Verificação inicial da quantidade ajustada contra a mínima permitida
        #if quantity < min_qty:
         #   print(f"Erro: Quantidade ajustada ({quantity}) é menor que o mínimo permitido ({min_qty}) para {symbol.replace('USDT', '')}.")
          #  return None

        # Obter o valor mínimo de notional, se presente
        filters = info['filters']
        min_notional = None
        for f in filters:
            if f['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(f['minNotional'])
                break

        # Calcula o valor total da compra
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        total_value = price * quantity

        # Logs adicionais para depuração
        print(f"Verificação de compra para {symbol.replace('USDT',' ')}")
        print(f"- Quantidade ajustada para compra: {quantity:.6f}")
        print(f"- Quantidade mínima permitida: {min_qty:.6f}")
        print(f"- Preço atual do ativo: {price:.6f} USDT")
        print(f"- Valor total da compra: {total_value:.6f} USDT")
        print(f"- Valor minimo para compra em USDT: {min_notional}USDT")
        if min_notional:
            print(f"Valor mínimo permitido (MIN_NOTIONAL): {min_notional:.6f} USDT")
        else:
            print(f"Valor mínimo permitido (MIN_NOTIONAL) não encontrado para {symbol}.")

        # Verifica se o valor total é suficiente
        if min_notional and total_value < min_notional:
            print(f"Erro: Valor total da compra ({total_value:.6f} USDT) é menor que o mínimo permitido ({min_notional:.6f} USDT).")
            return None

        # Realiza a compra
        order = client.order_market_buy(
            symbol=symbol,
            quantity=quantity
        )

        executed_qty = float(order['executedQty'])
        price = float(order['fills'][0]['price'])
        total_purchase_value = executed_qty * price

        wallet = get_wallet_assets()

        if symbol.replace('USDT', '') in wallet:
            wallet[symbol.replace('USDT', '')] += executed_qty
        else:
            wallet[symbol.replace('USDT', '')] = executed_qty
        wallet['USDT'] = wallet.get('USDT', 0) - total_purchase_value

        message = (f"====== Compra realizada! ===========\n"
                   f"Cripto: {symbol.replace('USDT', '')}\n"
                   f"Qtde da ordem executada: {executed_qty:.6f}\n"
                   f"Saldo total {symbol.replace('USDT', '')} em carteira: {wallet.get(symbol.replace('USDT', ''), 0):.6f}\n"
                   f"Saldo USDT disponível em carteira: {wallet['USDT']:.2f}\n")
        send_email("Compra Realizada", message)
        print(message)
        return order
    except BinanceAPIException as e:
        message = f"Erro ao realizar a compra de {symbol.replace('USDT', '')}: {e}"
        print(message)
        return None


# Função para realizar a venda
def sell_crypto(symbol, quantity):
    try:
        if config['modo_teste'] == True:
            message = f"[TEST MODE] Venda simulada: {symbol.replace('USDT', '')} - Quantidade: {quantity:.6f}"
            send_email("Venda Simulada", message)
            print(message)
            return {"status": "TEST", "symbol": symbol, "quantity": quantity}

        # Ajusta a quantidade conforme a precisão exigida
        quantity = adjust_quantity(symbol, quantity)

        # Obter as informações do símbolo
        info = client.get_symbol_info(symbol)
        lot_size_filter = next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')
        min_qty = float(lot_size_filter['minQty'])

        if quantity < min_qty:
            message = f"Erro: Quantidade ajustada ({quantity}) é menor que o mínimo permitido ({min_qty}) para {symbol.replace('USDT', '')}."
            print(message)
            return None

        # Obter o valor mínimo de notional, se presente
        filters = info['filters']
        min_notional = None
        for f in filters:
            if f['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(f['minNotional'])
                break

        # Se o filtro MIN_NOTIONAL não for encontrado, o código continua sem impedir a venda
        #if min_notional is None:
         #   print(f'Filtro "MIN_NOTIONAL" não encontrado para o símbolo {symbol}')

        # Verificar o valor total da venda
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        total_value = price * quantity

        if min_notional and total_value < min_notional:
            message = (f"Erro: Valor total da venda ({total_value:.2f} USDT) é menor que o mínimo permitido ({min_notional:.2f} USDT) para {symbol.replace('USDT', '')}.")
           # send_email("Erro na Venda", message)
            print(message)
            return None

        # Realiza a venda
        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )

        executed_qty = float(order['executedQty'])
        price = float(order['fills'][0]['price'])
        total_sale_value = executed_qty * price

        wallet = get_wallet_assets()

        if symbol.replace('USDT', '') in wallet:
            wallet[symbol.replace('USDT', '')] -= executed_qty
        else:
            wallet[symbol.replace('USDT', '')] = 0
        wallet['USDT'] = wallet.get('USDT', 0) + total_sale_value

        message = (f"====== Venda realizada! ===========\n"
                   f"Cripto: {symbol.replace('USDT', '')}\n"
                   f"Qtde da ordem executada: {executed_qty:.6f}\n"
                   f"Saldo total {symbol.replace('USDT', '')} em carteira: {wallet.get(symbol.replace('USDT', ''), 0):.6f}\n"
                   f"Saldo USDT disponível em carteira: {wallet['USDT']:.2f}\n")
        send_email("Venda Realizada", message)
        print(message)
        return order
    except BinanceAPIException as e:
        message = f"Erro ao realizar a venda de {symbol.replace('USDT', '')}: {e}"
       # send_email("Erro na Venda", message)
        print(message)
        return None
    
 
last_prices = {}  # Dicionário para armazenar o maior preço de cada ativo (não o anterior)
stop_loss_data = {}  # Dicionário para armazenar o stop loss calculado
trailing_activated = {}  # Dicionário para armazenar o status de ativação do trailing stop

def monitor_positions_from_wallet(trailing_stop_percentage=30.0, activation_threshold=30.0, min_stop_loss_percentage=7.0):


    """
    Monitora as posições na carteira e realiza vendas baseadas em trailing stop simplificado."""
    try:
        wallet_assets = get_wallet_assets(min_balance=0.1)

        if not wallet_assets:
            print("Nenhum ativo encontrado na carteira Spot com saldo suficiente. Encerrando análise.")
            return



        for asset, amount in wallet_assets.items():
            symbol = f"{asset}USDT"
            print(f"Analisando ativo {symbol.replace('USDT', '')}:")

            try:
                price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            except Exception as e:
                print(f"Erro ao obter preço de {symbol.replace('USDT', '')}: {e}")
                continue

            try:
                order_history = get_order_history(symbol=symbol)
            except Exception as e:
                print(f"Erro ao recuperar histórico de ordens para {symbol.replace('USDT', '')}: {e}")
                continue

            if not order_history:
                print(f"Nenhum histórico de ordens encontrado para {symbol.replace('USDT', '')}. Ignorando.")
                continue

            total_spent = 0.0
            total_qty = 0.0
            for order in order_history:
                if order['side'] == 'BUY' and order['status'] == 'FILLED':
                    total_spent += float(order['cummulativeQuoteQty'])
                    total_qty += float(order['executedQty'])           


            purchase_price = total_spent / total_qty if total_qty > 0 else price # Calculo do preço médio

            pnl_percent = ((price - purchase_price) / purchase_price) * 100 # Calculo do PNL

            print(f"- Quantidade: {amount:.6f}")
            print(f"- Preço atual: {price:.2f} USDT")
            print(f"- Preço de compra médio: {purchase_price:.2f} USDT")
            print(f"- PNL: {pnl_percent:.2f}%")

            # Ajusta a quantidade antes de tentar vender
            adjusted_quantity = adjust_quantity(symbol, amount)

            # Limita a quantidade ajustada ao saldo disponível
            if adjusted_quantity > amount:
                adjusted_quantity = amount

            print(f"- Quantidade ajustada para venda: {adjusted_quantity:.6f}")
            last_price2 = last_prices.get(symbol, 0)
            print(f"- Maior preço até o momento: {last_price2} USDT")

            if pnl_percent >= float(config['lucro_venda'].replace(',', '.')):
                # Venda normal se atingir a meta de lucro
                print(f"Lucro de {pnl_percent:.2f}% atingido para {symbol.replace('USDT', '')}. Vendendo {asset}.")
                sell_crypto(symbol, adjusted_quantity)

            # Atualiza o last_price independentemente do PNL
            last_price2 = last_prices.get(symbol, 0)
            if price > last_price2:
                last_prices[symbol] = price
                print(f"- Atualizado last_price para: {price:.2f} USDT")

            # Verifica se o PNL atingiu o limite para ativação do trailing stop
            if pnl_percent >= activation_threshold and not trailing_activated.get(symbol, False):
                trailing_activated[symbol] = True
                print("  - Trailing stop ativado!")

            if trailing_activated.get(symbol, False):
                # Calcula o stop loss com base no maior preço identificado
                stop_loss = last_prices[symbol] * (1 - trailing_stop_percentage / 100)

                # Verifica se o stop loss não pode ser inferior ao preço médio de compra + 7%
                if stop_loss < purchase_price + ((purchase_price * 7)/100) :
                    stop_loss = purchase_price * (1 + min_stop_loss_percentage / 100)  # Ajustando para 7% acima do preço médio
                    print(f"  - Stop loss ajustado para: {stop_loss:.2f} USDT devido à limitação mínima de 7% acima do preço médio de compra.")

                stop_loss_data[symbol] = stop_loss
                print(f"- Stop loss atualizado para: {stop_loss:.2f} USDT")

            else:
                print("- PNL não atingiu o limite para ativação do trailing stop.")

            # Verifica se a cotação atual atingiu o stop loss e desativa o trailing stop
            if trailing_activated.get(symbol, False):
                if price <= stop_loss_data.get(symbol, float('inf')):                    
                    print(f"  - Stop loss executado para o ativo {symbol.replace('USDT', '')}, vendendo ativo!")  
                    sell_crypto(symbol, adjusted_quantity)                  
                    trailing_activated[symbol] = False  # Desativa o trailing stop

    except BinanceAPIException as e:
        print(f"Erro ao monitorar as posições da carteira: {e}")
    except Exception as e:
        print(f"Erro inesperado ao monitorar a carteira: {e}")





# Função para verificar número de posições em aberto na carteira
def get_wallet_positions():
    """
    Retorna uma lista de posições (ativos com saldo > 0) na conta SPOT.
    """
    try:
        # Obter todos os ativos na carteira
        account_info = client.get_account()
        wallet_positions = []

        for balance in account_info['balances']:
            asset = balance['asset']
            free_amount = float(balance['free'])
            locked_amount = float(balance['locked'])

            # Considera uma posição apenas se houver saldo livre ou bloqueado
            if free_amount > 0 or locked_amount > 0:
                wallet_positions.append(asset)

        return wallet_positions
    except Exception as e:
        print(f"Erro ao obter posições da carteira: {e}")
        return []


def main():

    acesso.update_error_message("Running...")

    while True:
        global config
        global LIMIT_POSITION
        # Atualizar o valor de config chamando a função novamente
        config = acesso.get_config_from_spreadsheet()
       
        # Atualizar os parâmetros com base na nova configuração        
        PERCENTUAL_SALDO_COMPRA = float(config['saldo_a_usar'].replace(',', '.'))  # Garantir que seja um número decimal
        MIN_VOLUME = float(config['volume_minimo'])  # Garantir que seja um número decimal
        INTERVALO_ANALISE = int(config['intervalo_analise'])  # Se for inteiro, converte para int
        LIMITE_TOP_VOLATIL = int(config['limite_criptos'])  # Se for inteiro, converte para int
        HORAS_VOLATILIDADE = int(config['horas_volatilidade'])  # Se for inteiro, converte para int
        LIMIT_POSITION = int(config['limite_posicao'])  # Garantir que seja um número decimal
        PERCENTUAL_LUCRO = float(config['lucro_venda'])  # Garantir que seja um número decimal
        TEST_MODE = config['modo_teste']  # Caso a planilha retorne 'True' como string, converte para booleano 
        
        if config['on_off']:  # Verifica se o bot está ativado

            acesso.clear_column_a()

            print(f"Periodo de análise de volatilidade: {HORAS_VOLATILIDADE} hrs ")
            message = f"Periodo de análise de volatilidade: {HORAS_VOLATILIDADE} hrs "
            acesso.append_message(message)            
            print(f"Volume mínimo a considerar na análise: {MIN_VOLUME}")
            message = f"Volume mínimo a considerar na análise: {MIN_VOLUME}"
            acesso.append_message(message)
            print(f"% de saldo USDT à utilizar em cada compra: {PERCENTUAL_SALDO_COMPRA * 100}%")
            message = f"% de saldo USDT à utilizar em cada compra: {PERCENTUAL_SALDO_COMPRA * 100}%"
            acesso.append_message(message)
            print(f"Meta % de lucro definida: {PERCENTUAL_LUCRO}%")
            message = f"Meta % de lucro definida: {PERCENTUAL_LUCRO}%"
            acesso.append_message(message)
            print("Modo teste: Ativado" if TEST_MODE else "Modo teste: DESATIVADO!")
            message = "Modo teste: Ativado" if TEST_MODE else "Modo teste: DESATIVADO!"
            acesso.append_message(message)

            print("Iniciando análise de vendas...")
            data_hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            acesso.append_message(f"{data_hora_atual} - Iniciando análise de vendas...")

            

            monitor_positions_from_wallet()

            print("Iniciando análise de mercado e compras, por favor aguarde...")
            data_hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            acesso.append_message(f"{data_hora_atual} - Iniciando análise de mercado e compras, por favor aguarde...")

            # Obter criptos mais voláteis
            top_cryptos = get_top_volatile_cryptos(
                limit=LIMITE_TOP_VOLATIL,
                hours=HORAS_VOLATILIDADE,  # Passando o valor de HORAS_VOLATILIDADE
                min_volume=MIN_VOLUME
            )

            print("\nTop de Criptos Voláteis:")
            acesso.append_message("Top de Criptos Voláteis:")
            for i, crypto in enumerate(top_cryptos, start=1):
                symbol_without_usdt = crypto['symbol'].replace('USDT', '')  # Remove o sufixo 'USDT'
                volatility_percentage = crypto['volatility'] * 100  # Converte a volatilidade para porcentagem
                message = f"{i}. {symbol_without_usdt} - Volatilidade: {volatility_percentage:.2f}%" 
                data_hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                menssagedata= f"{data_hora_atual} - {message}"
                acesso.append_message(menssagedata)  # Inserir na planilha

                print(message)  # Exibir no console

            # Obter o número de posições atuais na carteira
            current_positions = len(get_wallet_positions())  # Função fictícia que retorna posições abertas

            if current_positions >= LIMIT_POSITION:
                print(f"Limite de {LIMIT_POSITION} posições simultâneas atingido. Nenhuma nova compra será realizada.")
            else:
                # Comprar as criptos mais voláteis até atingir o limite de posições
                for crypto in top_cryptos:
                    if current_positions >= LIMIT_POSITION:
                        print(f"Limite de {LIMIT_POSITION} posições simultâneas atingido. Parando as compras.")
                        break

                    symbol = crypto['symbol']
                    volatility = crypto['volatility']
                    balance = get_balance("USDT")
                    purchase_amount = balance * PERCENTUAL_SALDO_COMPRA

                    # Logs para depuração do saldo e do valor calculado para compra
                    #print(f"--- Informações de compra para {symbol} ---")
                    #print(f"Saldo total disponível em USDT: {balance:.6f}")
                    #print(f"Percentual configurado para uso: {PERCENTUAL_SALDO_COMPRA * 100:.2f}%")
                    #print(f"Valor calculado para compra: {purchase_amount:.6f} USDT")

                    print(f"Comprando {symbol.replace('USDT', '')} - Volatilidade: {volatility:.4f}")
                    buy_crypto(symbol, purchase_amount)
                    current_positions += 1  # Incrementa o número de posições abertas após cada compra

            if INTERVALO_ANALISE < 60:
                print(f"Aguardando intervalo de análise de {INTERVALO_ANALISE} segundo(s) ...")
            else:
                print(f"Aguardando intervalo de análise de {INTERVALO_ANALISE / 60} minuto(s) ...")

            time.sleep(INTERVALO_ANALISE)
        else:
            print("Bot desativado. Nenhuma ação será realizada.")
            time.sleep(60)  # Aguardar antes de verificar novamente


# Iniciar o bot com o tratamento de exceções
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = f"Ocorreu um erro fatal no robô: {str(e)}"
        additional_message = "O robô foi encerrado."
        send_email("Erro fatal no Robô de Trading", f"{error_message}\n\n{additional_message}")

        acesso.update_error_message("Encerrado")

        print("Erro fatal capturado. O robô foi encerrado.")
        exit(1)  # Encerra o robô após enviar o e-mail
        