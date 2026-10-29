# Execution interface references

Inspected October22,2026. Adapters use the standard library and fixed hosts;
there is no user-selectable production trading host.

- [Binance Spot Testnet REST contract](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/rest-api.md)
  specifies signed requests, client IDs, order queries and account balances.
- [Binance testnet filters](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/filters.md)
  supplies quantity/notional constraints. The adapter rounds quantities down and
  applies conservative size checks; actual market average-price filters can
  still reject an order, whose intent remains recorded.
- [Binance public-data REST contract](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md)
  identifies `data-api.binance.vision` for unauthenticated market data.
- [Alpaca crypto](https://docs.alpaca.markets/us/docs/crypto-trading)
  describes fractional crypto orders, asset increments and time-in-force.
- [Alpaca order lifecycle](https://docs.alpaca.markets/us/docs/working-with-orders)
  describes submission and client-order-ID tracking. Only the paper trading
  endpoint is used. Binance USDT signals versus Alpaca USD execution require
  an explicit quote-basis acknowledgement.

Mock contract tests are distinct from authenticated integration and actual
execution quality. No test in this repository fabricates a real fill.
