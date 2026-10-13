"""
Demand forecasting agent (network). Learns the calendar from traffic data.

It knows the date and time (a clock), never the calendar assumptions. A model
trained on a simulated year (training/train_models.py) predicts, for the coming
half hour, how busy the network will be and which direction dominates.
The corridor agent and the persona pages use the forecast.
Fallback without a model: no forecast (direction treated as balanced).
"""
from datetime import timedelta

from ...training.features import calendar_features
from ..base import Agent


class DemandForecastAgent(Agent):
    name = "demand_forecast"
    model_file = "demand_forecast.joblib"
    EVERY = 300

    def __init__(self, ctx):
        super().__init__(ctx)
        self.last = None

    def step(self, now):
        if self.last is not None and now - self.last < self.EVERY:
            return
        self.last = now
        when = self.ctx.clock(now) + timedelta(minutes=30)
        if self.model is None:
            self.bus.forecast = {"level": None, "inbound_share": 0.5, "method": "none"}
            return
        x = [calendar_features(when)]
        level = float(self.model["level"].predict(x)[0])
        share = float(self.model["inbound_share"].predict(x)[0])
        old = self.bus.forecast.get("level")
        self.bus.forecast = {"level": round(level, 3), "inbound_share": round(share, 3),
                             "for": when.strftime("%Y-%m-%d %H:%M"), "method": "model"}
        if old is None or abs(level - old) > 0.05:
            self.log.log(now, self.label, "publish", "FORECAST_UPDATE", level=level,
                         inbound_share=share, forecast_for=self.bus.forecast["for"])
