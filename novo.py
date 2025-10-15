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


# Obter saldo dos ativos da carteira   
def get_binance_balances(min_balance=0.0):
    try:
        # Obtém as informações de conta e saldo
        account_info = client.get_account()  # Retorna um dicionário
        
        # A lista de saldos está dentro da chave 'balances'
        balances = account_info['balances']
        
        wallet = {}
        for balance in balances:
            asset = balance['asset']
            free_balance = float(balance['free'])
            locked_balance = float(balance['locked'])
            
            # Filtra ativos com saldo total > min_balance e ignora BRL
            if asset not in ["BRL"] and (free_balance > min_balance or locked_balance > min_balance):
                wallet[asset] = {
                    "free": free_balance,
                    "locked": locked_balance,
                    "total": free_balance + locked_balance
                }
                
        return wallet

    except Exception as e:
        return f"Erro ao obter saldo: {str(e)}"

# Chamar a função e imprimir o saldo
saldo = get_binance_balances()
print(saldo)


# Obter o histórico de ordens
def get_order_history(symbol, limit=100, from_id=None):
    try:
        orders = []
        while True:
            params = {'symbol': symbol, 'limit': limit}
            if from_id:
                params['fromId'] = from_id

            # Chamar a API da Binance com os parâmetros
            response = client.get_all_orders(**params)
            
            if not response:
                break

            orders.extend(response)
            
            # Atualizar from_id para o próximo lote
            from_id = response[-1]['orderId']

            # Parar se o número de ordens retornadas for menor que o limite
            if len(response) < limit:
                break
        
        return orders
    
    except BinanceAPIException as e:
        print(f"Erro ao recuperar o histórico de ordens para {symbol}: {e}")
        return []


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
    


last_prices = {}  # Dicionário para armazenar o maior preço de cada ativo (não o anterior)
stop_loss_data = {}  # Dicionário para armazenar o stop loss calculado
trailing_activated = {}  # Dicionário para armazenar o status de ativação do trailing stop


# Analisar mercado para vendas
def monitor_positions_from_wallet(trailing_stop_percentage=30.0, activation_threshold=30.0, min_stop_loss_percentage=7.0):
    try:
        wallet_assets = get_binance_balances()
        if not wallet_assets:
            print("Nenhum ativo encontrado na carteira Spot com saldo suficiente. Encerrando análise.")
            return
        
    # Itera sobre cada ativo na carteira    
        for asset, amount in wallet_assets.items():
            symbol = f"{asset}USDT"
            print(f"Analisando ativo {symbol.replace('USDT', '')}:")

            try:
                # Obtém o preço atual do ativo
                price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            except Exception as e:
                # Trata erros ao obter o preço
                print(f"Erro ao obter preço de {symbol.replace('USDT', '')}: {e}")
                continue

            try:
                # Obtém o histórico de ordens do ativo
                order_history = get_order_history(symbol=symbol)
            except Exception as e:
                # Trata erros ao obter o histórico de ordens
                print(f"Erro ao recuperar histórico de ordens para {symbol.replace('USDT', '')}: {e}")
                continue

            # Verifica se não há histórico de ordens
            if not order_history:
                print(f"Nenhum histórico de ordens encontrado para {symbol.replace('USDT', '')}. Ignorando.")
                continue

            # Calcula o preço médio de compra e a quantidade total comprada
            total_spent = 0.0
            total_qty = 0.0
            for order in order_history:
                # Considera apenas ordens de compra preenchidas (limitadas ou de mercado)
                if (order['side'] == 'BUY' and order['status'] == 'FILLED') or (order['side'] == 'BUY' and order['type'] == 'MARKET'):
                    total_spent += float(order['cummulativeQuoteQty'])
                    total_qty += float(order['executedQty'])
            
            # Define o preço médio de compra ou usa o preço atual como fallback
            purchase_price = total_spent / total_qty if total_qty > 0 else price

            # Calcula o lucro ou prejuízo percentual (PNL)
            pnl_percent = ((price - purchase_price) / purchase_price) * 100

            # Ajusta a quantidade para venda (ex: limites mínimos da exchange)
            adjusted_quantity = adjust_quantity(symbol, amount)

            # Garante que a quantidade ajustada não exceda o saldo disponível
            if adjusted_quantity > amount:
                adjusted_quantity = amount

            # Obtém o maior preço registrado anteriormente
            last_price2 = last_prices.get(symbol, 0)           


            # Exibe detalhes da posição
            print(f"- Quantidade: {amount:.6f}")
            print(f"- Preço atual: {price:.2f} USDT")
            print(f"- Preço de compra médio: {purchase_price:.2f} USDT")
            print(f"- PNL: {pnl_percent:.2f}%")
            print(f"- Quantidade ajustada para venda: {adjusted_quantity:.6f}")
            print(f"- Maior preço até o momento: {last_price2} USDT")

            # Atualiza o maior preço registrado se o preço atual for superior
            if price > last_price2:
                last_prices[symbol] = price 
                print(f"- Atualizando maior preço para: {price:.2f} USDT")

            # Verifica se o PNL atingiu o limite de lucro para venda
            if pnl_percent >= float(config['lucro_venda'].replace(',', '.')):
                print(f"Lucro de {pnl_percent:.2f}% atingido para {symbol.replace('USDT', '')}. Vendendo {asset}.")
                #sell_crypto(symbol, adjusted_quantity)  # Realiza a venda

            # Ativa o trailing stop se o PNL atingir o limite
            if pnl_percent >= activation_threshold and not trailing_activated.get(symbol, False):
                trailing_activated[symbol] = True
                print("  - Trailing stop ativado!")
            
            # Calcula o valor do stop loss com base no maior preço registrado
            if trailing_activated.get(symbol, False):
                stop_loss = last_prices[symbol] * (1 - trailing_stop_percentage / 100)

                # Garante que o stop loss seja pelo menos 7% acima do preço médio de compra
                if stop_loss < purchase_price + ((purchase_price * 7)/100):
                    stop_loss = purchase_price + ((purchase_price * 7)/100)
                    print(f"  - Stop loss ajustado para: {stop_loss:.2f} USDT.")
                
                    # Armazena o valor do stop loss calculado
                    stop_loss_data[symbol] = stop_loss
                    print(f"- Stop loss atualizado para: {stop_loss:.2f} USDT")

        
            else:
                    print("- PNL não atingiu o limite para ativação do trailing stop.")

        # Verifica se o preço atual atingiu o stop loss configurado
            if trailing_activated.get(symbol, False):
                if price <= stop_loss_data.get(symbol, float('inf')):                    
                    #sell_crypto(symbol, adjusted_quantity)  # Realiza a venda
                    trailing_activated[symbol] = False  # Desativa o trailing stop
                    print(f"  - Stop loss executado para o ativo {symbol.replace('USDT', '')}, vendendo ativo!")  
                    

    except BinanceAPIException as e:
    # Trata erros específicos da API da Binance
        print(f"Erro ao monitorar as posições da carteira: {e}")
    except Exception as e:
    # Trata quaisquer outros erros inesperados
        print(f"Erro inesperado ao monitorar a carteira: {e}")


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


# Calcula o RSI
def calculate_rsi(symbol, interval='1h', periods=14):
    """
    Calcula o Índice de Força Relativa (RSI) para um ativo em um intervalo específico.

    :param symbol: Símbolo da criptomoeda, e.g., 'BTCUSDT'.
    :param interval: Intervalo das velas (e.g., '1h', '4h'). Default é '1h'.
    :param periods: Período para cálculo do RSI. Default é 14.
    :return: RSI calculado.
    """
    # Obter os dados de candles
    start_time = f"{2 * periods} hours ago UTC"  # Coletar mais dados para calcular suavização inicial
    klines = client.get_historical_klines(symbol, interval, start_time)
    
    # Extrair preços de fechamento
    closes = [float(kline[4]) for kline in klines]
    
    # Garantir que há dados suficientes para calcular o RSI
    if len(closes) < periods + 1:
        raise ValueError("Dados insuficientes para calcular o RSI.")
    
    # Calcular os deltas entre fechamentos consecutivos
    deltas = np.diff(closes)
    
    # Inicializar ganhos e perdas
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, abs(deltas), 0)
    
    # Calcular as médias iniciais
    avg_gain = np.mean(gains[:periods])
    avg_loss = np.mean(losses[:periods])
    
    # Aplicar suavização exponencial
    for i in range(periods, len(gains)):
        avg_gain = ((avg_gain * (periods - 1)) + gains[i]) / periods
        avg_loss = ((avg_loss * (periods - 1)) + losses[i]) / periods
    
    # Calcular RS e RSI
    rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
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
def get_top_volatile_cryptos(limit=int(config['limite_criptos']), 
                             hours=int(config['horas_volatilidade']), 
                             min_volume=float(config['volume_minimo'].replace(',', '.'))):
    try:
        # Obter a blacklist como um conjunto (para buscas mais rápidas)
        blacklist_criptos = set(acesso.get_blacklist_from_spreadsheet())
        
        # Obter os tickers e informações de negociação ativas
        tickers = client.get_ticker()
        #active_symbols = {symbol['symbol'] for symbol in client.get_exchange_info()['symbols'] if symbol['status'] == 'TRADING'}
        
        # Filtrar tickers para excluir blacklist e pares inativos
        filtered_tickers = [
            ticker for ticker in tickers
            if ticker['symbol'] not in blacklist_criptos
        ]
        
        # Obter os ativos da carteira
        wallet_assets = get_binance_balances(min_balance=1)
        
        # Processar os tickers em paralelo
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = list(executor.map(
                lambda ticker: process_ticker(ticker, min_volume, wallet_assets, hours),
                filtered_tickers
            ))
        
        # Filtrar resultados válidos e ordenar por volatilidade
        volatility_data = [result for result in results if result is not None]
        top_volatile = sorted(volatility_data, key=lambda x: x['volatility'], reverse=True)
        
        # Retornar os top N
        return top_volatile[:limit]
    
    except Exception as e:
        print(f"Erro ao obter criptos mais voláteis: {e}")
        return []
    

# Função para realizar a compra
def buy_crypto(symbol, quantity):
    try:
        if config['modo_teste'] == True:
            message = f"[TEST MODE] Compra simulada: {symbol.replace('USDT', '')} - Quantidade: {quantity:.6f}"
            send_email("Compra Simulada", message)
            print(message)
            return {"status": "TEST", "symbol": symbol, "quantity": quantity}

        # Obter o saldo disponível em USDT
        wallet = get_balance()
        saldo_usdt_disponivel = wallet.get('USDT', 0)

        # Calcular o valor a ser usado na compra
        saldo_a_usar = float(config['saldo_a_usar'].replace(',', '.')) * saldo_usdt_disponivel
        print(f"- Saldo a usar: {saldo_a_usar} USDT")
        print(f"- Saldo disponivel: {saldo_usdt_disponivel} USDT")

        if saldo_a_usar <= 0:
            print("Erro: Saldo insuficiente para realizar a compra.")
            return None

        # Obter o preço atual do ativo
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])

        # Obter as informações do símbolo
        info = client.get_symbol_info(symbol)
        lot_size_filter = next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')
        min_qty = float(lot_size_filter['minQty'])

        print(f"- Quantidade minima permitida para essa compra: {min_qty}")

        # Obter o valor mínimo de notional, se presente
        filters = info['filters']
        min_notional = None
        for f in filters:
            if f['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(f['minNotional'])
                break
        
        print(f"- Min_notional permitido para essa operação: {min_notional} USDT")

        # Ajustar a quantidade a ser comprada para respeitar o saldo disponível e os limites mínimos
        max_quantity = saldo_a_usar / price
        adjusted_quantity = adjust_quantity(symbol, max_quantity)

        print(f"- Quantidade ajustada para a compra: {adjusted_quantity}")

        # Verificar se a quantidade ajustada atende ao mínimo permitido
        if adjusted_quantity < min_qty:
            print(f"Erro: Quantidade ajustada ({adjusted_quantity:.6f}) é menor que o mínimo permitido ({min_qty:.6f}) para {symbol.replace('USDT', '')}.")
            return None

        # Calcula o valor total da compra
        total_value = price * adjusted_quantity

        # Verifica se o valor total é suficiente para o mínimo notional
        #if min_notional and total_value < min_notional:
         #   print(f"Erro: Valor total da compra ({total_value:.6f} USDT) é menor que o mínimo permitido ({min_notional:.6f} USDT).")
          #  return None

        # Verifica se o saldo disponível é suficiente para a compra
        if total_value > saldo_a_usar:
            print(f"Erro: O valor total da compra ({total_value:.6f} USDT) excede o saldo disponível ({saldo_a_usar:.6f} USDT).")
            return None

        # Realiza a compra
        order = client.order_market_buy(
            symbol=symbol,
            quantity=adjusted_quantity
        )

        executed_qty = float(order['executedQty'])
        price = float(order['fills'][0]['price'])
        total_purchase_value = executed_qty * price

        # Atualizar carteira após a compra
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


        # Verificar o valor total da venda
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        total_value = price * quantity

        #if min_notional and total_value < min_notional:
         #   message = (f"Erro: Valor total da venda ({total_value:.2f} USDT) é menor que o mínimo permitido ({min_notional:.2f} USDT) para {symbol.replace('USDT', '')}.")
           # send_email("Erro na Venda", message)
          #  print(message)
           # return None

        # Realiza a venda
        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )

        executed_qty = float(order['executedQty'])
        price = float(order['fills'][0]['price'])
        total_sale_value = executed_qty * price

        wallet = get_binance_balances()

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
    

# Função principal:
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
            current_positions = len(get_binance_balances()) 

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

        print(f"Erro fatal capturado {error_message}\n\n{additional_message}. O robô foi encerrado.")
        exit(1)  # Encerra o robô após enviar o e-mail
        
    
