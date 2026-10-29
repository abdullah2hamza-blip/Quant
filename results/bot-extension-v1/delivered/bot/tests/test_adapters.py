import copy
import json
from decimal import Decimal

import numpy as np
import pytest

from bot_io import AlpacaPaper, BinancePaper, ApiError, PublicFeed, Http, BINANCE, ALPACA, PUBLIC
from paper_engine.data import Bars


class HttpFixture:
    def __init__(self):
        self.calls=[]
        self.answer={}
    def request(self,base,method,path,**kw):
        self.calls.append((base,method,path,kw))
        value=self.answer[path]
        if isinstance(value,Exception):raise value
        return copy.deepcopy(value)


@pytest.fixture
def http():
    h=HttpFixture()
    h.answer['/api/v3/time']={'serverTime':1792674000000}
    h.answer['/api/v3/exchangeInfo']={'symbols':[{'status':'TRADING','baseAsset':'BTC','quoteAsset':'USDT','filters':[
        {'filterType':'LOT_SIZE','stepSize':'0.00001','minQty':'0.00001','maxQty':'10'},
        {'filterType':'MARKET_LOT_SIZE','stepSize':'0.00001','minQty':'0.00001','maxQty':'5'},
        {'filterType':'MIN_NOTIONAL','minNotional':'5','applyToMarket':True}]}]}
    h.answer['/api/v3/order']={'clientOrderId':'paper-id','symbol':'BTCUSDT','status':'FILLED','executedQty':'0.01'}
    h.answer['/v2/orders']={'client_order_id':'paper-id','symbol':'BTC/USD','status':'filled'}
    h.answer['/v2/orders:by_client_order_id']=h.answer['/v2/orders']
    h.answer['/v2/assets']=[{'symbol':'BTC/USD','status':'active','tradable':True,'min_trade_increment':'0.00000001','min_order_size':'0.0001'}]
    return h


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    for name in ('BINANCE_TESTNET_KEY','BINANCE_TESTNET_SECRET','ALPACA_API_KEY','ALPACA_API_SECRET'):
        monkeypatch.setenv(name,'fictional-test-credential')


def test_binance_signatures_and_submission_are_only_testnet(http):
    broker=BinancePaper(http)
    order=broker.prepare('buy',.010009,50_000,'paper-id')
    assert Decimal(order['quantity'])==Decimal('0.01000')
    result=broker.submit(order)
    assert result['status']=='FILLED'
    assert all(base==BINANCE for base,_,_,_ in http.calls)
    signed=http.calls[-1][3]
    assert len(signed['params']['signature'])==64
    assert signed['params']['newClientOrderId']=='paper-id'
    assert signed['headers']['X-MBX-APIKEY']=='fictional-test-credential'


@pytest.mark.parametrize('qty',[.000001,.00002,10.01])
def test_exchange_minimum_and_maximum_filters_prevent_invalid_order(http,qty):
    assert BinancePaper(http).prepare('buy',qty,50_000,'paper-id') is None


def test_alpaca_fractional_quantity_and_crypto_time_in_force(http):
    broker=AlpacaPaper(http)
    order=broker.prepare('sell',.010000009,50_000,'paper-id')
    assert order['qty']=='0.01000000' and order['time_in_force']=='gtc'
    broker.submit(order)
    assert all(base==ALPACA for base,_,_,_ in http.calls)
    assert http.calls[-1][3]['payload']==order


def test_alpaca_cash_not_margin_buying_power(http):
    http.answer['/v2/account']={'status':'ACTIVE','cash':'1000','buying_power':'4000'}
    http.answer['/v2/positions']=[{'symbol':'BTCUSD','qty':'0.1'}]
    assert AlpacaPaper(http).balance()==(1000.,.1)


def test_locked_inventory_and_other_positions_are_not_ignored(http):
    http.answer['/api/v3/account']={'canTrade':True,'balances':[{'asset':'BTC','free':'1','locked':'0.1'}]}
    with pytest.raises(RuntimeError,match='Locked'):
        BinancePaper(http).balance()
    http.answer['/v2/account']={'status':'ACTIVE','cash':'1000'}
    http.answer['/v2/positions']=[{'symbol':'AAPL','qty':'1'}]
    with pytest.raises(ValueError,match='dedicated'):
        AlpacaPaper(http).balance()


@pytest.mark.parametrize('name,path,not_found',[('binance','/api/v3/order',ApiError(400,-2013)),('alpaca','/v2/orders:by_client_order_id',ApiError(404))])
def test_only_documented_missing_order_responses_return_none(http,name,path,not_found):
    broker=BinancePaper(http) if name=='binance' else AlpacaPaper(http)
    http.answer[path]=not_found
    assert broker.query('paper-id') is None
    http.answer[path]=ApiError(500)
    with pytest.raises(ApiError):broker.query('paper-id')


def test_wrong_order_identity_is_not_accepted_as_reconciliation(http):
    http.answer['/api/v3/order']['clientOrderId']='someone-else'
    with pytest.raises(RuntimeError,match='identity'):
        BinancePaper(http).query('paper-id')
    http.answer['/v2/orders:by_client_order_id']['symbol']='ETH/USD'
    with pytest.raises(RuntimeError,match='identity'):
        AlpacaPaper(http).query('paper-id')


def test_missing_credentials_never_fall_back_to_a_different_account(monkeypatch,http):
    monkeypatch.delenv('BINANCE_TESTNET_KEY')
    with pytest.raises(ValueError,match='TESTNET'):
        BinancePaper(http)


@pytest.mark.parametrize('base',['http://testnet.binance.vision','https://api.binance.com','https://api.alpaca.markets','https://example.com'])
def test_transport_rejects_production_and_unconfigured_hosts_without_network(base):
    with pytest.raises(ValueError,match='endpoint'):
        Http().request(base,'POST','/api/v3/order')


def test_public_append_retains_history_and_excludes_open_candle(http):
    step=14_400_000;t=1504224000000
    bars=Bars(np.array([t,t+step]),np.array([[100,101,99,100,1],[100,102,99,101,2.]]),np.array([t,t+step])+step-1,'4h',{})
    http.answer['/api/v3/klines']=[[t+2*step,'101','103','100','102','3',t+3*step-1,0,0,0,0,0],
        [t+3*step,'102','104','101','103','4',t+4*step-1,0,0,0,0,0]]
    out=PublicFeed(http).update(bars,t+3*step+1)
    assert len(out)==3
    np.testing.assert_array_equal(out.values[:2],bars.values)
    assert all(base==PUBLIC and method=='GET' for base,method,_,_ in http.calls)
    http.answer['/api/v3/klines']=[[]]
    with pytest.raises(ValueError,match='Malformed'):
        PublicFeed(http).update(bars,t+3*step+1)
