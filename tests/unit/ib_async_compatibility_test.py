"""Contract smoke for the maintained IBKR client; never opens a socket."""

from inspect import signature


def test_ib_async_provides_the_read_adapter_contract_without_connecting():
    from ib_async import IB, Stock, ExecutionFilter

    required = {
        "host",
        "port",
        "clientId",
        "timeout",
        "readonly",
        "account",
        "raiseSyncErrors",
    }
    assert required <= set(signature(IB.connect).parameters)
    assert callable(IB.qualifyContracts)
    assert callable(IB.managedAccounts)
    assert callable(IB.disconnect)
    assert ExecutionFilter

    client = IB()
    assert client.RequestTimeout == 0
    assert client.RaiseRequestErrors is False

    contract = Stock("SPYL", "IBIS2", "EUR")
    assert (contract.symbol, contract.exchange, contract.currency) == (
        "SPYL",
        "IBIS2",
        "EUR",
    )
    assert not client.isConnected()
