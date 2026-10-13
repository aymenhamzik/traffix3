"""
Weather agent (network). Turns the weather feed into directives.

  rain    -> WEATHER_TIMING directive to every master: longer yellow and clearance
  flood   -> FLOOD publication: rerouting avoids the road, pages are warned
Learned (models/rain_speed.joblib): how much rain slows traffic, published so
the incident agent and the pages can expect it.
"""
from ...core.messages import Message
from ..base import Agent


class WeatherAgent(Agent):
    name = "weather"
    model_file = "rain_speed.joblib"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.rain, self.floods = 0.0, set()

    def step(self, now):
        rain = self.sensors.weather.get("rain", 0.0)
        if rain != self.rain:
            self.rain = rain
            factor = float(self.model.predict([[rain]])[0]) if self.model is not None else 1 - 0.2 * rain
            self.bus.publish(Message(self.label, "WEATHER", "all", now, now + 1e9, "rain",
                                     details={"intensity": rain, "expected_speed_factor": round(factor, 2)}))
            self.log.log(now, self.label, "directive", "WEATHER_RAIN" if rain > 0 else "WEATHER_CLEAR",
                         intensity=rain, expected_speed_factor=factor)
        if self.rain > 0:
            w = self.cfg["weather"]
            for tls in self.ctx.models:
                self.send("WEATHER_TIMING", tls, now, ttl=10, subject="rain",
                          extra_yellow=w["rain_extra_yellow"], extra_clearance=w["rain_extra_clearance"])
        for edge in self.sensors.weather.get("flood_alerts", []):
            if edge not in self.floods:
                self.floods.add(edge)
                self.bus.publish(Message(self.label, "FLOOD", "all", now, now + 1e9, edge))
                self.log.log(now, self.label, "publish", "WEATHER_FLOOD", edge=edge)
