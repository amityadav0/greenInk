"""Cost of a call, from the price table in `config/models.yaml`."""

from greenink.llm.router import ModelPrice

_PER = 1_000_000


def cost_usd(price: ModelPrice, tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * price.input + tokens_out * price.output) / _PER
